"""
Unit & End-to-End Tests for Traffic Intelligence System
======================================================
"""

import sys
import os
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


class TestDatasetAndLoader(unittest.TestCase):
    def test_network_graph_build(self):
        from backend.core.network_graph import get_network_graph
        g = get_network_graph()
        self.assertGreater(len(g.G.nodes), 50)
        self.assertGreater(len(g.G.edges), 100)
        self.assertIn("R0001", g.segments)

    def test_upstream_downstream_traversal(self):
        from backend.core.network_graph import get_network_graph
        g = get_network_graph()
        up = g.get_upstream_segments("R0001", depth=2)
        down = g.get_downstream_segments("R0001", depth=2)
        self.assertIsInstance(up, list)
        self.assertIsInstance(down, list)

    def test_geojson_export(self):
        from backend.core.network_graph import get_network_graph
        g = get_network_graph()
        gj = g.to_geojson()
        self.assertEqual(gj["type"], "FeatureCollection")
        self.assertGreater(len(gj["features"]), 100)


class TestFeatureEngineering(unittest.TestCase):
    def test_feature_columns_extraction(self):
        import pandas as pd
        from ml.features.feature_engineering import get_feature_columns
        df = pd.DataFrame({
            "timestamp": ["2026-01-01"],
            "segment_id": ["R0001"],
            "speed_kmh": [50.0],
            "target_speed_15m": [55.0], # Target - must be excluded
            "hour": [12],
        })
        cols = get_feature_columns(df)
        self.assertIn("speed_kmh", cols)
        self.assertIn("hour", cols)
        self.assertNotIn("target_speed_15m", cols)
        self.assertNotIn("timestamp", cols)


class TestIntelligenceModules(unittest.TestCase):
    def test_congestion_propagation(self):
        from backend.core.network_graph import get_network_graph
        from backend.intelligence.congestion_propagation import CongestionPropagationAnalyzer
        g = get_network_graph()
        analyzer = CongestionPropagationAnalyzer(g, {"R0001": 0.45})
        res = analyzer.analyze("R0001", max_depth=2)
        self.assertEqual(res["origin_segment"], "R0001")
        self.assertEqual(res["origin_severity"], "severe")
        self.assertIsInstance(res["affected_segments"], list)

    def test_bottleneck_detection(self):
        import pandas as pd
        from backend.core.network_graph import get_network_graph
        from backend.intelligence.bottleneck_detection import BottleneckDetector
        g = get_network_graph()
        detector = BottleneckDetector(g)
        
        # Mock traffic & network df
        traffic_mock = pd.DataFrame({
            "segment_id": ["R0001", "R0001"],
            "congestion_index": [0.4, 0.5],
            "flow_vph": [2000, 2200],
            "queue_length_veh": [10, 15],
            "delay_min": [2.0, 3.0]
        })
        network_mock = pd.DataFrame({
            "segment_id": ["R0001"],
            "capacity_vph": [2000],
            "lanes": [2],
            "importance": [0.8],
            "structural_bottleneck": [1],
            "road_class": ["arterial"],
            "length_km": [1.0]
        })

        top = detector.get_top_bottlenecks(traffic_mock, network_mock, top_n=1)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0]["segment_id"], "R0001")
        self.assertGreater(top[0]["bottleneck_score"], 0.4)

    def test_intervention_engine(self):
        from backend.core.network_graph import get_network_graph
        from backend.intelligence.intervention_engine import InterventionEngine
        g = get_network_graph()
        engine = InterventionEngine(g, {"R0001": 0.5})
        cand = {
            "candidate_id": "PLAN001",
            "target_segment": "R0001",
            "intervention_type": "capacity_upgrade",
            "capacity_delta_vph": 500,
            "cost_index": 10,
            "feasibility_band": "medium"
        }
        res = engine.score_candidate(cand)
        self.assertEqual(res["candidate_id"], "PLAN001")
        self.assertGreater(res["priority_score"], 0)


if __name__ == "__main__":
    unittest.main()
