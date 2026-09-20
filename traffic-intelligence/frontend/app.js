// NEURAX Cyberpunk Traffic Intelligence Platform — Frontend JS

const API_BASE = window.location.origin;

let map;
let geojsonLayer = null;
let currentHorizon = '15m';
let selectedSegmentId = null;
let networkData = null;
let forecastDataMap = {};
let chartCongestion = null;
let chartSpeedFlow = null;

const CYBER_COLORS = {
    free: '#00ff9d',
    moderate: '#ffe600',
    heavy: '#ff6600',
    severe: '#ff0055',
    selected: '#00f3ff',
    magenta: '#ff007f'
};

document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initCharts();
    setupEventListeners();
    loadDashboardData();
    setInterval(loadDashboardData, 30000); // refresh every 30s
});

// Initialize Leaflet Map with CARTO Dark Matter Cyberpunk base tiles
function initMap() {
    map = L.map('map').setView([17.38, 78.44], 12);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; NEURAX GRID &copy; OpenStreetMap &copy; CARTO',
        maxZoom: 18,
    }).addTo(map);
}

// Setup Event Listeners
function setupEventListeners() {
    document.querySelectorAll('.horizon-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.horizon-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentHorizon = btn.dataset.h;
            updateMapStyle();
            if (selectedSegmentId) inspectSegment(selectedSegmentId);
        });
    });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(btn.dataset.tab).classList.add('active');
        });
    });

    document.getElementById('btn-run-whatif').addEventListener('click', runWhatIfSimulation);

    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.main-view').forEach(v => v.style.display = 'none');
            btn.classList.add('active');
            document.getElementById(btn.dataset.view).style.display = 'block';
            if(btn.dataset.view === 'map-view') {
                map.invalidateSize(); // Fix leaflet sizing issue when map becomes visible again
                if (typeof stopVisualSimulation === 'function') stopVisualSimulation();
            }
        });
    });

    document.getElementById('btn-run-lab').addEventListener('click', runScenarioLab);
}

// Load Dashboard Data
async function loadDashboardData() {
    try {
        const [health, network, forecast, incidents, bottlenecks, interventions] = await Promise.all([
            fetch(`${API_BASE}/health`).then(r => r.json()),
            fetch(`${API_BASE}/network`).then(r => r.json()),
            fetch(`${API_BASE}/traffic/forecast?horizon=${currentHorizon}`).then(r => r.json()),
            fetch(`${API_BASE}/incidents`).then(r => r.json()),
            fetch(`${API_BASE}/bottlenecks?top_n=10`).then(r => r.json()),
            fetch(`${API_BASE}/interventions?top_n=10`).then(r => r.json())
        ]);

        document.getElementById('time-val').innerText = health.latest_timestamp || 'LIVE GRID';
        networkData = network;

        forecastDataMap = {};
        if (forecast.segments) {
            forecast.segments.forEach(s => {
                forecastDataMap[s.segment_id] = s;
            });
        }

        renderNetworkMap(network);
        updateKPIs(forecast.segments, incidents, bottlenecks);
        renderBottlenecks(bottlenecks.bottlenecks);
        renderInterventions(interventions.interventions);
        document.getElementById('inc-count').innerText = incidents.count || 0;

    } catch (e) {
        console.error('Failed to load cyberpunk matrix data:', e);
    }
}

// Map color lookup
function getCyberColor(level) {
    return CYBER_COLORS[level] || CYBER_COLORS.free;
}

// Render Network GeoJSON Vector Grid
function renderNetworkMap(geojson) {
    if (geojsonLayer) map.removeLayer(geojsonLayer);

    geojsonLayer = L.geoJSON(geojson, {
        style: (feature) => {
            const sid = feature.properties.segment_id;
            const fData = forecastDataMap[sid];
            const color = fData ? getCyberColor(fData.congestion_level) : CYBER_COLORS.free;
            const weight = (sid === selectedSegmentId) ? 7 : (fData && fData.congestion_index > 0.15 ? 4.5 : 3);
            return {
                color: color,
                weight: weight,
                opacity: 0.9,
                lineCap: 'round'
            };
        },
        onEachFeature: (feature, layer) => {
            const sid = feature.properties.segment_id;
            layer.on({
                click: () => {
                    selectedSegmentId = sid;
                    updateMapStyle();
                    inspectSegment(sid);
                },
                mouseover: () => {
                    const fData = forecastDataMap[sid];
                    const congStr = fData ? (fData.congestion_index * 100).toFixed(1) + '%' : '0.0%';
                    layer.bindTooltip(`<div style="font-family:'Orbitron'; font-weight:700; color:#00f3ff;">${sid}</div><div style="font-family:'Share Tech Mono'; color:#fff;">Grid Class: ${feature.properties.road_class}<br>Congestion: ${congStr}</div>`, { sticky: true }).openTooltip();
                }
            });
        }
    }).addTo(map);

    if (!selectedSegmentId && geojson.features.length > 0) {
        map.fitBounds(geojsonLayer.getBounds());
    }
}

function updateMapStyle() {
    if (geojsonLayer) {
        geojsonLayer.setStyle((feature) => {
            const sid = feature.properties.segment_id;
            const fData = forecastDataMap[sid];
            const color = fData ? getCyberColor(fData.congestion_level) : CYBER_COLORS.free;
            const isSelected = (sid === selectedSegmentId);
            return {
                color: isSelected ? CYBER_COLORS.selected : color,
                weight: isSelected ? 8 : (fData && fData.congestion_index > 0.15 ? 4.5 : 3),
                opacity: isSelected ? 1.0 : 0.85
            };
        });
    }
}

// Update Left Panel KPIs
function updateKPIs(segments, incidents, bottlenecks) {
    if (!segments) return;
    document.getElementById('kpi-total').innerText = segments.length;
    const severe = segments.filter(s => s.congestion_level === 'severe').length;
    const heavy = segments.filter(s => s.congestion_level === 'heavy').length;
    document.getElementById('kpi-severe').innerText = severe;
    document.getElementById('kpi-heavy').innerText = heavy;
    document.getElementById('kpi-bottlenecks').innerText = (bottlenecks.bottlenecks || []).length;
}

// Render Top Bottlenecks List
function renderBottlenecks(list) {
    const container = document.getElementById('bottleneck-list');
    if (!list || list.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.8rem;">No critical bottlenecks detected</div>';
        return;
    }
    container.innerHTML = list.map(b => `
        <div style="background: rgba(10, 14, 26, 0.8); padding: 8px 10px; border-radius: 4px; cursor: pointer; border-left: 3px solid var(--cyber-orange); border-bottom: 1px solid rgba(255,255,255,0.05);" onclick="inspectSegment('${b.segment_id}')">
            <div style="display: flex; justify-content: space-between; font-family:'Orbitron'; font-size: 0.8rem; font-weight:700;">
                <span style="color: var(--cyber-cyan);">${b.segment_id}</span>
                <span style="color: var(--cyber-orange)">SCORE: ${(b.bottleneck_score * 100).toFixed(0)}%</span>
            </div>
            <div style="font-family:'Share Tech Mono'; font-size: 0.75rem; color: var(--text-muted); margin-top: 3px;">
                ${b.reason[0] || 'High queue pressure'}
            </div>
        </div>
    `).join('');
}

// Render Ranked Interventions
function renderInterventions(list) {
    const container = document.getElementById('intervention-details');
    if (!list || list.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No candidates available.</p>';
        return;
    }
    container.innerHTML = list.slice(0, 5).map(item => `
        <div style="background: var(--cyber-black); border: 1px solid var(--cyber-border); border-radius: 4px; padding: 10px; margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; font-family:'Orbitron'; font-size: 0.8rem; color: var(--cyber-cyan);">
                <span>${item.candidate_id} [${item.segment_id}]</span>
                <span style="color: var(--cyber-magenta)">PRIORITY: ${(item.priority_score * 100).toFixed(0)}</span>
            </div>
            <div style="font-size: 0.85rem; margin: 4px 0;"><b>ACTION:</b> ${item.intervention_type} (+${item.capacity_delta_vph} vph)</div>
            <div style="font-family:'Share Tech Mono'; font-size: 0.75rem; color: var(--text-muted);">
                BENEFIT: ${(item.estimated_benefit_score * 100).toFixed(1)}% | FEASIBILITY: ${item.feasibility_band.toUpperCase()}
            </div>
            <div class="disclaimer-tag">${item.disclaimer}</div>
        </div>
    `).join('');
}

// Inspect Selected Segment
async function inspectSegment(segmentId) {
    selectedSegmentId = segmentId;
    updateMapStyle();

    const titleEl = document.getElementById('selected-seg-title');
    const segDetailsEl = document.getElementById('seg-details');
    const propDetailsEl = document.getElementById('propagation-details');

    titleEl.innerHTML = `<i class="fa-solid fa-crosshairs"></i> VECTOR: ${segmentId}`;
    segDetailsEl.innerHTML = '<p style="color: var(--text-muted); font-family:\'Share Tech Mono\';">Scanning link telemetry...</p>';

    try {
        const data = await fetch(`${API_BASE}/traffic/segment/${segmentId}`).then(r => r.json());
        const curr = data.current_state;
        const net = data.network;

        const statusColor = getCyberColor(curr.congestion_level);

        segDetailsEl.innerHTML = `
            <div class="detail-row"><span>STATUS</span><span class="detail-val" style="color: ${statusColor}; text-shadow: 0 0 8px ${statusColor};">${curr.congestion_level.toUpperCase()}</span></div>
            <div class="detail-row"><span>SPEED</span><span class="detail-val">${curr.speed_kmh.toFixed(1)} km/h</span></div>
            <div class="detail-row"><span>FLOW</span><span class="detail-val">${curr.flow_vph.toFixed(0)} vph</span></div>
            <div class="detail-row"><span>CAPACITY</span><span class="detail-val">${net.capacity_vph} vph (${net.lanes} lanes)</span></div>
            <div class="detail-row"><span>CLASS</span><span class="detail-val">${net.road_class.toUpperCase()}</span></div>
            <div class="detail-row"><span>BOTTLENECK FLAG</span><span class="detail-val">${net.structural_bottleneck ? 'YES' : 'NO'}</span></div>
            
            <h4 style="margin-top: 12px; font-family:'Orbitron'; font-size: 0.75rem; color: var(--cyber-cyan);">XAI NEURAL CONTRIBUTION PROXY</h4>
            <div style="font-family:'Share Tech Mono'; font-size: 0.75rem; background: var(--cyber-black); border: 1px solid var(--cyber-border); padding: 8px; border-radius: 4px; margin-top: 4px;">
                ${renderXAI(data.explanation)}
            </div>
        `;

        // Propagation
        const prop = await fetch(`${API_BASE}/propagation/${segmentId}`).then(r => r.json());
        propDetailsEl.innerHTML = `
            <div class="detail-row"><span>ORIGIN CONGESTION</span><span class="detail-val">${(prop.origin_congestion * 100).toFixed(1)}%</span></div>
            <div class="detail-row"><span>AFFECTED LINKS</span><span class="detail-val">${prop.total_affected} roads</span></div>
            <div class="detail-row"><span>SPILLBACK DEPTH</span><span class="detail-val">${prop.propagation_depth} hops</span></div>
            <div class="detail-row"><span>CONFIDENCE</span><span class="detail-val">${(prop.confidence * 100).toFixed(0)}%</span></div>
            <div style="margin-top: 8px; max-height: 150px; overflow-y: auto;">
                ${(prop.affected_segments || []).map(s => `
                    <div style="font-family:'Share Tech Mono'; font-size: 0.75rem; padding: 4px 0; border-bottom: 1px solid var(--cyber-border); display: flex; justify-content: space-between;">
                        <span>${s.segment_id} [${s.direction}]</span>
                        <span style="color: var(--cyber-orange)">EST: ${(s.estimated_congestion * 100).toFixed(1)}%</span>
                    </div>
                `).join('')}
            </div>
            <div class="disclaimer-tag">${prop.disclaimer}</div>
        `;

        updateCharts(data.forecast, curr);

    } catch (e) {
        console.error('Error fetching segment details:', e);
    }
}

function renderXAI(explanation) {
    if (!explanation || !explanation.congestion || !explanation.congestion.top_features) {
        return 'No explanation matrix available.';
    }
    const top = explanation.congestion.top_features;
    return Object.entries(top).slice(0, 4).map(([f, val]) => `
        <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
            <span>${f}</span>
            <span style="color: var(--cyber-cyan)">${val.toFixed(3)}</span>
        </div>
    `).join('');
}

// Run What-If Counterfactual
async function runWhatIfSimulation() {
    if (!selectedSegmentId) {
        alert('Select a road link vector on the grid matrix first.');
        return;
    }
    const resEl = document.getElementById('whatif-result');
    resEl.innerHTML = '<p style="color: var(--cyber-cyan); font-family:\'Share Tech Mono\'; font-size: 0.8rem;">Executing ML counterfactual estimation...</p>';

    try {
        const res = await fetch(`${API_BASE}/counterfactual`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                segment_id: selectedSegmentId,
                intervention_type: 'capacity_upgrade',
                capacity_delta_vph: 500,
                horizon: currentHorizon
            })
        }).then(r => r.json());

        resEl.innerHTML = `
            <div style="background: var(--cyber-black); border: 1px solid var(--cyber-cyan); box-shadow: 0 0 10px rgba(0,243,255,0.2); padding: 10px; border-radius: 4px; font-size: 0.8rem;">
                <div style="font-family:'Orbitron'; font-weight: 700; color: var(--cyber-cyan); margin-bottom: 4px;">SCENARIO SIMULATION [${res.source.toUpperCase()}]</div>
                <div class="detail-row"><span>BASELINE CONGESTION</span><span class="detail-val">${(res.baseline.congestion_index * 100).toFixed(1)}%</span></div>
                <div class="detail-row"><span>INTERVENTION SCENARIO</span><span class="detail-val" style="color: var(--cyber-green); text-shadow: 0 0 8px var(--cyber-green);">${(res.intervention_scenario.congestion_index * 100).toFixed(1)}%</span></div>
                <div class="detail-row"><span>CONGESTION REDUCTION</span><span class="detail-val" style="color: var(--cyber-green); text-shadow: 0 0 8px var(--cyber-green);">${(res.delta.congestion_reduction * 100).toFixed(1)}%</span></div>
                <div class="detail-row"><span>SPEED DELTA</span><span class="detail-val" style="color: var(--cyber-cyan);">+${res.delta.speed_improvement_kmh} km/h</span></div>
                <div class="disclaimer-tag">${res.disclaimer}</div>
            </div>
        `;
    } catch (e) {
        resEl.innerHTML = '<p style="color: var(--cyber-red); font-size: 0.8rem;">Simulation failed.</p>';
    }
}

// Initialize Cyberpunk Chart.js Timelines
function initCharts() {
    Chart.defaults.font.family = "'Share Tech Mono', monospace";
    Chart.defaults.color = '#64748b';

    const ctx1 = document.getElementById('chart-congestion').getContext('2d');
    chartCongestion = new Chart(ctx1, {
        type: 'line',
        data: {
            labels: ['NOW', '+15M', '+30M', '+45M', '+60M'],
            datasets: [{
                label: 'CONGESTION INDEX FORECAST',
                borderColor: '#ff6600',
                backgroundColor: 'rgba(255, 102, 0, 0.15)',
                data: [0, 0, 0, 0, 0],
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                pointBackgroundColor: '#ff6600'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#00f3ff', font: { family: 'Orbitron', size: 10 } } } },
            scales: {
                x: { ticks: { color: '#64748b' }, grid: { color: '#1e2942' } },
                y: { ticks: { color: '#64748b' }, grid: { color: '#1e2942' }, min: 0 }
            }
        }
    });

    const ctx2 = document.getElementById('chart-speed-flow').getContext('2d');
    chartSpeedFlow = new Chart(ctx2, {
        type: 'line',
        data: {
            labels: ['NOW', '+15M', '+30M', '+45M', '+60M'],
            datasets: [
                {
                    label: 'PREDICTED SPEED (KM/H)',
                    borderColor: '#00f3ff',
                    data: [0, 0, 0, 0, 0],
                    yAxisID: 'y',
                    pointRadius: 4,
                    pointBackgroundColor: '#00f3ff'
                },
                {
                    label: 'PREDICTED FLOW (VPH)',
                    borderColor: '#00ff9d',
                    data: [0, 0, 0, 0, 0],
                    yAxisID: 'y1',
                    pointRadius: 4,
                    pointBackgroundColor: '#00ff9d'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#00f3ff', font: { family: 'Orbitron', size: 10 } } } },
            scales: {
                x: { ticks: { color: '#64748b' }, grid: { color: '#1e2942' } },
                y: { position: 'left', ticks: { color: '#00f3ff' }, grid: { color: '#1e2942' } },
                y1: { position: 'right', ticks: { color: '#00ff9d' }, grid: { drawOnChartArea: false } }
            }
        }
    });
}

function updateCharts(forecast, curr) {
    if (!forecast) return;

    const horizons = ['+15m', '+30m', '+45m', '+60m'];
    const congVals = [curr.congestion_index, ...horizons.map(h => (forecast[h] && forecast[h].congestion) || 0)];
    const speedVals = [curr.speed_kmh, ...horizons.map(h => (forecast[h] && forecast[h].speed) || 0)];
    const flowVals = [curr.flow_vph, ...horizons.map(h => (forecast[h] && forecast[h].flow) || 0)];

    chartCongestion.data.datasets[0].data = congVals;
    chartCongestion.update();

    chartSpeedFlow.data.datasets[0].data = speedVals;
    chartSpeedFlow.data.datasets[1].data = flowVals;
    chartSpeedFlow.update();
}

// Run SUMO Scenario Lab
async function runScenarioLab() {
    const net = document.getElementById('lab-network').value;
    const demand = document.getElementById('lab-demand').value;
    const disruption = document.getElementById('lab-disruption').value;

    const statusEl = document.getElementById('lab-status');
    const resultEl = document.getElementById('sumo-results');

    // Switch view to SUMO automatically
    document.querySelector('.view-btn[data-view="sumo-view"]').click();

    statusEl.innerHTML = '<span style="color: var(--cyber-yellow);"><i class="fa-solid fa-spinner fa-spin"></i> QUEUED...</span>';
    resultEl.innerHTML = renderSumoRunning(net, demand, disruption);
    
    // Start Canvas Simulation Animation
    startVisualSimulation(net, demand, disruption);

    try {
        const submitRes = await fetch(`${API_BASE}/sumo/run`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ network: net, demand: demand, disruption: disruption })
        }).then(r => r.json());

        // If already complete (mock), render immediately
        if (submitRes.status === 'COMPLETED' && submitRes.mean_travel_time_s !== undefined) {
            statusEl.innerHTML = '<span style="color: var(--cyber-green);"><i class="fa-solid fa-check"></i> COMPLETED</span>';
            resultEl.innerHTML = renderSumoResults(submitRes, net, demand, disruption);
            return;
        }

        const runId = submitRes.run_id;
        if (!runId) { throw new Error(submitRes.message || 'No run_id returned'); }
        statusEl.innerHTML = `<span style="color: var(--cyber-yellow);"><i class="fa-solid fa-spinner fa-spin"></i> RUNNING [${runId}]...</span>`;

        // Poll for completion (max 120s)
        let metrics = null;
        for (let i = 0; i < 120; i++) {
            await new Promise(r => setTimeout(r, 1000));
            const poll = await fetch(`${API_BASE}/sumo/results/${runId}`).then(r => r.json());
            if (poll.status === 'COMPLETED' && poll.metrics) {
                metrics = poll.metrics;
                break;
            } else if (poll.status === 'FAILED') {
                throw new Error('Simulation FAILED on backend.');
            }
        }

        if (!metrics) { throw new Error('Simulation timed out.'); }

        statusEl.innerHTML = '<span style="color: var(--cyber-green);"><i class="fa-solid fa-check"></i> COMPLETED</span>';
        resultEl.innerHTML = renderSumoResults(metrics, net, demand, disruption);

    } catch (e) {
        statusEl.innerHTML = `<span style="color: var(--cyber-red);"><i class="fa-solid fa-xmark"></i> FAILED: ${e.message}</span>`;
        resultEl.innerHTML = `<h3 style="color:var(--cyber-red);text-align:center;margin-top:30%">SIMULATION FAILED</h3><p style="color:#aaa;text-align:center;">${e.message}</p>`;
    }
}

function renderSumoRunning(net, demand, disruption) {
    return `
        <div style="text-align:center; margin-top: 15%;">
            <div style="font-size:3em; color:var(--cyber-cyan); margin-bottom:20px;"><i class="fa-solid fa-satellite-dish fa-spin"></i></div>
            <h2 style="color:var(--cyber-cyan);font-family:'Orbitron';">SIMULATION RUNNING</h2>
            <p style="color:#aaa;margin-top:10px;font-family:'Share Tech Mono';">${net.replace('_',' ').toUpperCase()} · ${demand.replace('_',' ').toUpperCase()} · ${disruption.replace('_',' ').toUpperCase()}</p>
        </div>`;
}

function renderSumoResults(m, net, demand, disruption) {
    const utilPct = ((m.capacity_utilization || 0) * 100).toFixed(1);
    const congColor = {free:'var(--cyber-green)', moderate:'var(--cyber-yellow)', heavy:'var(--cyber-orange)', severe:'var(--cyber-red)'}[m.congestion_level] || 'var(--cyber-green)';
    const isMock = (m.source !== 'sumo_simulation');

    return `
        <div style="max-width:700px; margin:0 auto; padding:20px;">
            ${isMock ? `<div style="background:rgba(255,230,0,0.1);border:1px solid var(--cyber-yellow);padding:8px 12px;border-radius:4px;font-size:0.8rem;color:var(--cyber-yellow);margin-bottom:16px;"><i class="fa-solid fa-triangle-exclamation"></i> SUMO not installed — mock estimates shown. Install SUMO + set SUMO_HOME for real simulation.</div>` : ''}
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
                ${kpiCard('TRAVEL TIME', (m.mean_travel_time_s||0).toFixed(1)+' s', '#fff')}
                ${kpiCard('MEAN SPEED', (m.mean_speed_kmh||0).toFixed(1)+' km/h', 'var(--cyber-cyan)')}
                ${kpiCard('QUEUE LENGTH', (m.mean_queue_length_veh||0).toFixed(1)+' veh', 'var(--cyber-orange)')}
                ${kpiCard('THROUGHPUT', (m.mean_throughput_vph||0).toFixed(0)+' vph', 'var(--cyber-green)')}
                ${kpiCard('TOTAL DELAY', (m.total_delay_veh_h||0).toFixed(1)+' veh·h', 'var(--cyber-red)')}
                ${kpiCard('CAPACITY UTIL', utilPct+'%', congColor)}
            </div>
            <div style="background:rgba(0,0,0,0.5);border:1px solid var(--cyber-border);border-radius:4px;padding:12px;">
                <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                    <span style="font-family:'Orbitron';font-size:0.8rem;color:var(--cyber-cyan);">CONGESTION LEVEL</span>
                    <span style="font-weight:700;color:${congColor};text-shadow:0 0 8px ${congColor};">${(m.congestion_level||'').toUpperCase()}</span>
                </div>
                <div class="detail-row"><span>SCENARIO</span><span class="detail-val">${(m.scenario_id||'').replace(/_/g,' ')}</span></div>
                <div class="detail-row"><span>DISRUPTION FACTOR</span><span class="detail-val">${((m.capacity_factor||1)*100).toFixed(0)}% capacity</span></div>
                <div class="detail-row"><span>SOURCE</span><span class="detail-val" style="color:${isMock?'var(--cyber-yellow)':'var(--cyber-green)'};">${m.source||'unknown'}</span></div>
            </div>
            <div style="margin-top:12px;background:rgba(255,230,0,0.06);border:1px solid rgba(255,230,0,0.2);padding:8px;border-radius:4px;font-size:0.75rem;color:var(--cyber-yellow);">${m.disclaimer||''}</div>
        </div>`;
}

function kpiCard(label, value, color) {
    return `<div style="background:var(--cyber-panel);border:1px solid var(--cyber-border);border-radius:4px;padding:10px 14px;flex:1;min-width:100px;">
        <div style="font-family:'Orbitron';font-size:1.1rem;font-weight:900;color:${color};">${value}</div>
        <div style="font-size:0.7rem;color:var(--text-muted);margin-top:2px;">${label}</div>
    </div>`;
}

// ----------------------------------------------------
// Video Stream Renderer
// ----------------------------------------------------

function stopVisualSimulation() {
    document.getElementById('sumo-canvas').style.display = 'none';
}

function startVisualSimulation(net, demand, disruption) {
    const img = document.getElementById('sumo-canvas');
    img.style.display = 'block';
    // Append timestamp to bust cache and restart stream
    img.src = `/sumo/stream?t=${new Date().getTime()}`;
}
