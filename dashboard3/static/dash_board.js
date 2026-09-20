// Smart Traffic Dashboard JavaScript
// Connects your HTML frontend to the Flask backend

class TrafficDashboard {
    constructor() {
        this.isFullscreen = false;
        this.statusUpdateInterval = null;
        this.init();
    }

    init() {
        console.log('🚦 Traffic Dashboard initializing...');
        this.startStatusUpdates();
        this.setupEventListeners();
    }

    startStatusUpdates() {
        // Update status every 1 second for better responsiveness
        this.statusUpdateInterval = setInterval(() => {
            this.updateStatus();
        }, 1000);
        
        // Initial update
        this.updateStatus();
    }

    setupEventListeners() {
        // Handle window resize for responsive design
        window.addEventListener('resize', () => {
            this.handleResize();
        });
        
        // Handle fullscreen changes
        document.addEventListener('fullscreenchange', () => {
            this.isFullscreen = !this.isFullscreen;
            this.updateFullscreenButton();
        });
    }

    async updateStatus() {
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            // Update status display
            const elements = ['mode', 'phase', 'flow', 'status', 'emergency'];
            elements.forEach(id => {
                const element = document.getElementById(id);
                if (element && data[id]) {
                    element.textContent = data[id];
                }
            });
            
            // Update emergency status color
            const emergencyElement = document.getElementById('emergency');
            if (emergencyElement) {
                if (data.emergency === 'Active') {
                    emergencyElement.style.color = '#ff4444';
                    emergencyElement.style.fontWeight = 'bold';
                } else {
                    emergencyElement.style.color = '#4CAF50';
                    emergencyElement.style.fontWeight = 'normal';
                }
            }
            
            // Update traffic lights
            const intersectionCount = Object.keys(data.intersections || {}).length;
            console.log(`Found ${intersectionCount} active intersections:`, Object.keys(data.intersections || {}));
            this.updateTrafficLights(data.intersections || {});
            
            // Update metrics if available
            if (data.metrics) {
                this.updateMetrics(data.metrics);
            }
            
        } catch (error) {
            console.error('❌ Error updating status:', error);
            this.showError('Connection lost. Retrying...');
        }
    }

    updateTrafficLights(intersections) {
        // Update only intersections that have actual data
        const intersectionIds = ['A', 'B', 'C', 'D'];
        
        intersectionIds.forEach(intersection => {
            const lightElement = document.getElementById(`light${intersection}`);
            if (lightElement) {
                const state = intersections[intersection];
                
                if (state) {
                    // Show intersection with real SUMO data
                    lightElement.style.display = 'flex';
                    
                    // Reset all lights
                    const lights = lightElement.querySelectorAll('.light');
                    lights.forEach(light => {
                        light.classList.remove('active');
                    });
                    
                    // Activate current phase light
                    const redLight = lightElement.querySelector('.light.red');
                    const yellowLight = lightElement.querySelector('.light.yellow');
                    const greenLight = lightElement.querySelector('.light.green');
                    
                    if (state.green && greenLight) {
                        greenLight.classList.add('active');
                    } else if (state.yellow && yellowLight) {
                        yellowLight.classList.add('active');
                    } else if (redLight) {
                        redLight.classList.add('active');
                    }
                    
                    // Update lane information
                    this.updateLaneInfo(intersection, state.lanes || {});
                    
                    // Update intersection name
                    const nameElement = lightElement.querySelector('.intersection-name');
                    if (nameElement) {
                        nameElement.textContent = `Intersection ${intersection}`;
                        nameElement.style.opacity = '1';
                    }
                } else {
                    // Hide intersection if no data
                    lightElement.style.display = 'none';
                }
            }
        });
    }
    
    updateLaneInfo(intersection, lanes) {
        // Update lane-specific information with individual signals
        const directions = ['North', 'South', 'East', 'West'];
        
        directions.forEach(direction => {
            const laneElement = document.getElementById(`lane${intersection}-${direction}`);
            const signalElement = document.getElementById(`signal${intersection}-${direction}`);
            
            if (laneElement) {
                const laneData = lanes[direction] || { 
                    vehicles: 0, 
                    waiting_time: 0, 
                    signal: 'red'
                };
                
                const vehiclesSpan = laneElement.querySelector('.vehicles');
                const waitSpan = laneElement.querySelector('.wait');
                
                if (vehiclesSpan) {
                    vehiclesSpan.textContent = laneData.vehicles || 0;
                }
                if (waitSpan) {
                    const waitTime = laneData.waiting_time || 0;
                    waitSpan.textContent = `${waitTime}s`;
                }
                
                // Update individual lane signal
                if (signalElement) {
                    const signal = laneData.signal || 'red';
                    if (signal === 'green') {
                        signalElement.textContent = '🟢';
                    } else if (signal === 'yellow') {
                        signalElement.textContent = '🟡';
                    } else {
                        signalElement.textContent = '🔴';
                    }
                }
                
                // Add congestion indicator
                const waitTime = laneData.waiting_time || 0;
                if (waitTime > 30) {
                    laneElement.classList.add('congested');
                } else {
                    laneElement.classList.remove('congested');
                }
            }
        });
    }

    updateMetrics(metrics) {
        // Add metrics display to the dashboard if elements exist
        const metricsElements = {
            'total-vehicles': metrics.total_vehicles,
            'avg-waiting': `${metrics.avg_waiting_time?.toFixed(1)}s`,
            'throughput': `${metrics.throughput}/min`,
            'congestion': `${metrics.congestion_level}%`,
            'emergency-count': metrics.emergency_vehicles
        };

        Object.keys(metricsElements).forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = metricsElements[id];
            }
        });

        // Update congestion level color
        const congestionElement = document.getElementById('congestion');
        if (congestionElement && metrics.congestion_level !== undefined) {
            const level = metrics.congestion_level;
            if (level > 70) {
                congestionElement.style.color = '#ff4444';
            } else if (level > 40) {
                congestionElement.style.color = '#ff8800';
            } else {
                congestionElement.style.color = '#4CAF50';
            }
        }
    }

    async sendControl(action) {
        try {
            console.log(`🎮 Sending control: ${action}`);
            
            const response = await fetch('/api/control', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ action: action })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showSuccess(result.message);
                // Force immediate status update
                setTimeout(() => this.updateStatus(), 500);
            } else {
                this.showError(result.message || 'Command failed');
            }
            
        } catch (error) {
            console.error('❌ Control error:', error);
            this.showError('Failed to send command');
        }
    }

    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showError(message) {
        this.showNotification(message, 'error');
    }

    showNotification(message, type) {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 4px;
            color: white;
            font-weight: bold;
            z-index: 1000;
            animation: slideIn 0.3s ease;
            background-color: ${type === 'success' ? '#4CAF50' : '#f44336'};
        `;
        
        document.body.appendChild(notification);
        
        // Auto remove after 3 seconds
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }

    handleResize() {
        // Handle responsive design
        const sumoStream = document.getElementById('sumoStream');
        if (sumoStream && window.innerWidth < 768) {
            sumoStream.style.width = '100%';
            sumoStream.style.height = 'auto';
        }
    }

    updateFullscreenButton() {
        const fullscreenBtn = document.querySelector('[onclick="fullscreenSim()"]');
        if (fullscreenBtn) {
            fullscreenBtn.textContent = this.isFullscreen ? 'Exit Fullscreen' : 'Fullscreen';
        }
    }
}

// Global control functions called by your HTML buttons
async function startSim() {
    await dashboard.sendControl('start');
}

async function stopSim() {
    await dashboard.sendControl('stop');
}

async function resetSim() {
    if (confirm('Are you sure you want to reset the simulation?')) {
        await dashboard.sendControl('reset');
    }
}

function fullscreenSim() {
    const sumoStream = document.getElementById('sumoStream');
    
    if (!dashboard.isFullscreen) {
        if (sumoStream.requestFullscreen) {
            sumoStream.requestFullscreen();
        } else if (sumoStream.webkitRequestFullscreen) {
            sumoStream.webkitRequestFullscreen();
        } else if (sumoStream.msRequestFullscreen) {
            sumoStream.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
    }
}

// Signal control functions
async function setSignal(signalType) {
    console.log(`🚦 Setting signal: ${signalType}`);
    
    // Visual feedback - highlight clicked button briefly
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(btn => {
        if (btn.getAttribute('onclick') === `setSignal('${signalType}')`) {
            btn.style.transform = 'scale(0.95)';
            setTimeout(() => {
                btn.style.transform = 'scale(1)';
            }, 150);
        }
    });
    
    await dashboard.sendControl(`signal_${signalType}`);
}

// Advanced features
class AdvancedFeatures {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.metricsChart = null;
        this.setupAdvancedFeatures();
    }

    setupAdvancedFeatures() {
        // Add keyboard shortcuts
        this.setupKeyboardShortcuts();
        
        // Add real-time metrics display
        this.createMetricsDisplay();
        
        // Add auto-refresh toggle
        this.addAutoRefreshToggle();
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey) {
                switch(e.key) {
                    case 'p':
                        e.preventDefault();
                        playSim();
                        break;
                    case 'r':
                        e.preventDefault();
                        resetSim();
                        break;
                    case 'f':
                        e.preventDefault();
                        fullscreenSim();
                        break;
                    case '1':
                        e.preventDefault();
                        setSignal('ns_green');
                        break;
                    case '2':
                        e.preventDefault();
                        setSignal('ew_green');
                        break;
                    case 'e':
                        e.preventDefault();
                        setSignal('emergency');
                        break;
                }
            }
        });

        // Add keyboard shortcuts help
        this.addKeyboardHelp();
    }

    addKeyboardHelp() {
        const helpButton = document.createElement('button');
        helpButton.textContent = '?';
        helpButton.className = 'btn help-btn';
        helpButton.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            border: none;
            background: #2196F3;
            color: white;
            font-size: 18px;
            cursor: pointer;
            z-index: 1000;
        `;
        
        helpButton.onclick = () => {
            alert(`Keyboard Shortcuts:
Ctrl+P - Play/Start Simulation
Ctrl+R - Reset Simulation  
Ctrl+F - Fullscreen
Ctrl+1 - NS Green
Ctrl+2 - EW Green
Ctrl+E - Emergency Mode`);
        };
        
        document.body.appendChild(helpButton);
    }

    createMetricsDisplay() {
        // Add a metrics panel if it doesn't exist
        const existingMetrics = document.getElementById('metrics-panel');
        if (existingMetrics) return;

        const metricsPanel = document.createElement('div');
        metricsPanel.id = 'metrics-panel';
        metricsPanel.innerHTML = `
            <div class="card">
                <h3>Live Metrics</h3>
                <div class="metrics-grid">
                    <div class="metric">
                        <span class="metric-label">Vehicles:</span>
                        <span id="total-vehicles" class="metric-value">0</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Avg Wait:</span>
                        <span id="avg-waiting" class="metric-value">0s</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Throughput:</span>
                        <span id="throughput" class="metric-value">0/min</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Congestion:</span>
                        <span id="congestion" class="metric-value">0%</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Emergency:</span>
                        <span id="emergency-count" class="metric-value">0</span>
                    </div>
                </div>
            </div>
        `;

        // Add some basic styles
        metricsPanel.style.cssText = `
            position: fixed;
            top: 20px;
            left: 20px;
            background: rgba(0,0,0,0.8);
            color: white;
            padding: 15px;
            border-radius: 8px;
            font-family: Arial, sans-serif;
            z-index: 999;
            max-width: 200px;
        `;

        document.body.appendChild(metricsPanel);
    }

    addAutoRefreshToggle() {
        const refreshToggle = document.createElement('button');
        refreshToggle.textContent = '⏸️ Pause Updates';
        refreshToggle.className = 'btn gray';
        refreshToggle.style.cssText = `
            position: fixed;
            top: 20px;
            right: 80px;
            z-index: 1000;
        `;

        let paused = false;
        refreshToggle.onclick = () => {
            paused = !paused;
            if (paused) {
                clearInterval(this.dashboard.statusUpdateInterval);
                refreshToggle.textContent = '▶️ Resume Updates';
            } else {
                this.dashboard.startStatusUpdates();
                refreshToggle.textContent = '⏸️ Pause Updates';
            }
        };

        document.body.appendChild(refreshToggle);
    }
}

// Initialize dashboard when page loads
let dashboard;
let advancedFeatures;

document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 Initializing Traffic Dashboard...');
    
    // Create main dashboard instance
    dashboard = new TrafficDashboard();
    
    // Initialize advanced features
    advancedFeatures = new AdvancedFeatures(dashboard);
    
    // Add CSS animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
        
        .light.active {
            box-shadow: 0 0 20px currentColor;
            filter: brightness(1.5);
        }
        
        .btn:active {
            transform: scale(0.95);
        }
        
        .metrics-grid {
            display: grid;
            gap: 10px;
        }
        
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid rgba(255,255,255,0.2);
        }
        
        .metric-label {
            font-size: 12px;
            opacity: 0.8;
        }
        
        .metric-value {
            font-weight: bold;
            font-size: 14px;
        }
    `;
    document.head.appendChild(style);
    
    console.log('✅ Dashboard initialized successfully!');
});