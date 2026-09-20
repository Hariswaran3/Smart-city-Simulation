"""
Network Graph Module
====================
Builds a directed graph of the road network using NetworkX.
Supports: upstream/downstream lookup, neighbor queries,
          reachability, route traversal, bottleneck detection,
          congestion propagation, affected-area calculation.

Designed to be SUMO-compatible (same node/segment IDs).
"""

import logging
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class SegmentInfo:
    """Static attributes of a road segment."""
    segment_id: str
    source_node: str
    target_node: str
    road_class: str
    lanes: int
    free_flow_speed_kmh: float
    capacity_vph: float
    length_km: float
    grade_pct: float
    signal_id: Optional[str]
    structural_bottleneck: int
    importance: float
    peak_capacity_factor: float


@dataclass
class NodeInfo:
    """Geographic and signal attributes of a network node."""
    node_id: str
    lat: float
    lon: float
    x: float
    y: float
    signal: Optional[dict] = None  # signal plan if present


class TrafficNetworkGraph:
    """
    Directed graph of the road network.

    Nodes = intersections/junctions (from nodes.csv)
    Edges = road segments (from network.csv)

    Each edge carries full SegmentInfo as attributes.
    """

    def __init__(self):
        self.G: nx.DiGraph = nx.DiGraph()
        self.segments: Dict[str, SegmentInfo] = {}     # segment_id → SegmentInfo
        self.nodes: Dict[str, NodeInfo] = {}           # node_id → NodeInfo
        self.signal_plans: Dict[str, dict] = {}        # signal_id → plan
        self.turn_restrictions: List[dict] = []
        self._segment_to_edge: Dict[str, Tuple[str, str]] = {}  # seg_id → (src, tgt)
        self._edge_to_segment: Dict[Tuple[str, str], str] = {}  # (src, tgt) → seg_id

    # -----------------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------------

    def build(self,
              network_df: pd.DataFrame,
              nodes_df: pd.DataFrame,
              signal_plans_df: Optional[pd.DataFrame] = None,
              turn_restrictions_df: Optional[pd.DataFrame] = None) -> "TrafficNetworkGraph":
        """
        Construct the graph from dataset DataFrames.
        """
        # Build signal plan lookup
        if signal_plans_df is not None:
            for _, row in signal_plans_df.iterrows():
                self.signal_plans[row["signal_id"]] = {
                    "signal_id": row["signal_id"],
                    "node_id": row["node_id"],
                    "cycle_s": row["cycle_s"],
                    "green_ratio": row["green_ratio"],
                    "offset_s": row["offset_s"],
                }

        # Add nodes
        for _, row in nodes_df.iterrows():
            nid = row["node_id"]
            ni = NodeInfo(
                node_id=nid,
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                x=float(row["x"]),
                y=float(row["y"]),
            )
            self.nodes[nid] = ni
            self.G.add_node(nid, lat=ni.lat, lon=ni.lon, x=ni.x, y=ni.y)

        # Add edges (segments)
        for _, row in network_df.iterrows():
            sid = row["segment_id"]
            src = row["source_node"]
            tgt = row["target_node"]

            si = SegmentInfo(
                segment_id=sid,
                source_node=src,
                target_node=tgt,
                road_class=str(row.get("road_class", "unknown")),
                lanes=int(row.get("lanes", 1)),
                free_flow_speed_kmh=float(row.get("free_flow_speed_kmh", 50)),
                capacity_vph=float(row.get("capacity_vph", 1800)),
                length_km=float(row.get("length_km", 1.0)),
                grade_pct=float(row.get("grade_pct", 0)),
                signal_id=row.get("signal_id") if pd.notna(row.get("signal_id")) else None,
                structural_bottleneck=int(row.get("structural_bottleneck", 0)),
                importance=float(row.get("importance", 0.5)),
                peak_capacity_factor=float(row.get("peak_capacity_factor", 1.0)),
            )
            self.segments[sid] = si
            self._segment_to_edge[sid] = (src, tgt)
            self._edge_to_segment[(src, tgt)] = sid

            travel_time_h = si.length_km / si.free_flow_speed_kmh if si.free_flow_speed_kmh > 0 else 0.1
            self.G.add_edge(src, tgt,
                            segment_id=sid,
                            weight=travel_time_h * 60,  # travel time in minutes
                            **{k: v for k, v in si.__dict__.items()
                               if k not in ("source_node", "target_node", "segment_id")})

        # Turn restrictions
        if turn_restrictions_df is not None:
            self.turn_restrictions = turn_restrictions_df.to_dict(orient="records")

        logger.info("Graph built: %d nodes, %d segments", len(self.G.nodes), len(self.G.edges))
        return self

    # -----------------------------------------------------------------------
    # Traversal helpers
    # -----------------------------------------------------------------------

    def get_segment_info(self, segment_id: str) -> Optional[SegmentInfo]:
        return self.segments.get(segment_id)

    def get_upstream_segments(self, segment_id: str, depth: int = 2) -> List[str]:
        """Return segments that feed into the given segment (up to `depth` hops)."""
        info = self.segments.get(segment_id)
        if info is None:
            return []
        # Predecessors of the source node
        result = []
        visited = set()
        frontier = {info.source_node}
        for _ in range(depth):
            next_frontier = set()
            for node in frontier:
                for pred in self.G.predecessors(node):
                    edge_key = (pred, node)
                    seg = self._edge_to_segment.get(edge_key)
                    if seg and seg not in visited and seg != segment_id:
                        result.append(seg)
                        visited.add(seg)
                        next_frontier.add(pred)
            frontier = next_frontier
        return result

    def get_downstream_segments(self, segment_id: str, depth: int = 2) -> List[str]:
        """Return segments reachable from the given segment (up to `depth` hops)."""
        info = self.segments.get(segment_id)
        if info is None:
            return []
        result = []
        visited = set()
        frontier = {info.target_node}
        for _ in range(depth):
            next_frontier = set()
            for node in frontier:
                for succ in self.G.successors(node):
                    edge_key = (node, succ)
                    seg = self._edge_to_segment.get(edge_key)
                    if seg and seg not in visited and seg != segment_id:
                        result.append(seg)
                        visited.add(seg)
                        next_frontier.add(succ)
            frontier = next_frontier
        return result

    def get_neighboring_segments(self, segment_id: str) -> List[str]:
        """Return segments sharing a node with the given segment."""
        info = self.segments.get(segment_id)
        if info is None:
            return []
        neighbors = set()
        for node in [info.source_node, info.target_node]:
            for pred in self.G.predecessors(node):
                seg = self._edge_to_segment.get((pred, node))
                if seg and seg != segment_id:
                    neighbors.add(seg)
            for succ in self.G.successors(node):
                seg = self._edge_to_segment.get((node, succ))
                if seg and seg != segment_id:
                    neighbors.add(seg)
        return list(neighbors)

    def get_reachable_segments(self, segment_id: str,
                                max_depth: int = 3,
                                direction: str = "downstream") -> List[str]:
        """Return all reachable segments in a given direction."""
        if direction == "downstream":
            return self.get_downstream_segments(segment_id, depth=max_depth)
        elif direction == "upstream":
            return self.get_upstream_segments(segment_id, depth=max_depth)
        else:
            return list(set(
                self.get_upstream_segments(segment_id, depth=max_depth) +
                self.get_downstream_segments(segment_id, depth=max_depth)
            ))

    def find_shortest_path(self,
                            from_segment: str,
                            to_segment: str) -> Optional[List[str]]:
        """Find shortest path between two segments (by free-flow travel time)."""
        src_info = self.segments.get(from_segment)
        tgt_info = self.segments.get(to_segment)
        if src_info is None or tgt_info is None:
            return None
        try:
            node_path = nx.shortest_path(
                self.G, source=src_info.target_node,
                target=tgt_info.source_node, weight="weight"
            )
            seg_path = [from_segment]
            for i in range(len(node_path) - 1):
                seg = self._edge_to_segment.get((node_path[i], node_path[i + 1]))
                if seg:
                    seg_path.append(seg)
            seg_path.append(to_segment)
            return seg_path
        except nx.NetworkXNoPath:
            return None

    def find_alternative_routes(self,
                                  from_node: str,
                                  to_node: str,
                                  k: int = 3) -> List[List[str]]:
        """Find k shortest simple paths between nodes. Returns lists of segment IDs."""
        try:
            paths = []
            for node_path in nx.shortest_simple_paths(self.G, from_node, to_node, weight="weight"):
                seg_path = []
                for i in range(len(node_path) - 1):
                    seg = self._edge_to_segment.get((node_path[i], node_path[i + 1]))
                    if seg:
                        seg_path.append(seg)
                if seg_path:
                    paths.append(seg_path)
                if len(paths) >= k:
                    break
            return paths
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    # -----------------------------------------------------------------------
    # Bottleneck detection
    # -----------------------------------------------------------------------

    def get_structural_bottlenecks(self) -> List[str]:
        """Return segments flagged as structural bottlenecks in the network."""
        return [
            sid for sid, info in self.segments.items()
            if info.structural_bottleneck == 1
        ]

    def compute_betweenness(self, normalized: bool = True) -> Dict[str, float]:
        """Compute edge betweenness centrality (proxy for network importance)."""
        edge_bc = nx.edge_betweenness_centrality(self.G, weight="weight", normalized=normalized)
        seg_bc = {}
        for (src, tgt), val in edge_bc.items():
            seg = self._edge_to_segment.get((src, tgt))
            if seg:
                seg_bc[seg] = val
        return seg_bc

    def get_segment_capacity(self, segment_id: str) -> float:
        info = self.segments.get(segment_id)
        return info.capacity_vph if info else 0.0

    def get_node_coords(self, node_id: str) -> Optional[Tuple[float, float]]:
        """Return (lat, lon) for a node."""
        info = self.nodes.get(node_id)
        return (info.lat, info.lon) if info else None

    def get_segment_coords(self, segment_id: str) -> Optional[dict]:
        """Return source and target coordinates for a segment."""
        info = self.segments.get(segment_id)
        if info is None:
            return None
        src_coords = self.get_node_coords(info.source_node)
        tgt_coords = self.get_node_coords(info.target_node)
        if src_coords and tgt_coords:
            return {
                "source": {"lat": src_coords[0], "lon": src_coords[1]},
                "target": {"lat": tgt_coords[0], "lon": tgt_coords[1]},
                "midpoint": {
                    "lat": (src_coords[0] + tgt_coords[0]) / 2,
                    "lon": (src_coords[1] + tgt_coords[1]) / 2,
                }
            }
        return None

    def to_geojson(self) -> dict:
        """Export the road network as a GeoJSON FeatureCollection."""
        features = []
        for seg_id, info in self.segments.items():
            coords = self.get_segment_coords(seg_id)
            if coords is None:
                continue
            src = coords["source"]
            tgt = coords["target"]
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [src["lon"], src["lat"]],
                        [tgt["lon"], tgt["lat"]]
                    ]
                },
                "properties": {
                    "segment_id": seg_id,
                    "source_node": info.source_node,
                    "target_node": info.target_node,
                    "road_class": info.road_class,
                    "lanes": info.lanes,
                    "capacity_vph": info.capacity_vph,
                    "free_flow_speed_kmh": info.free_flow_speed_kmh,
                    "length_km": info.length_km,
                    "structural_bottleneck": info.structural_bottleneck,
                    "importance": info.importance,
                }
            }
            features.append(feature)
        return {"type": "FeatureCollection", "features": features}

    def to_nodes_geojson(self) -> dict:
        """Export nodes as GeoJSON FeatureCollection."""
        features = []
        for nid, info in self.nodes.items():
            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [info.lon, info.lat]},
                "properties": {"node_id": nid}
            }
            features.append(feature)
        return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Singleton builder
# ---------------------------------------------------------------------------

_graph_instance: Optional[TrafficNetworkGraph] = None


def get_network_graph(force_rebuild: bool = False) -> TrafficNetworkGraph:
    """Return a cached TrafficNetworkGraph, building it if necessary."""
    global _graph_instance
    if _graph_instance is None or force_rebuild:
        import sys
        sys.path.insert(0, r"d:\data-urban\traffic-intelligence")
        from ml.preprocessing.data_loader import (
            load_network, load_nodes, load_signal_plans, load_turn_restrictions
        )
        network_df = load_network()
        nodes_df = load_nodes()
        signal_df = load_signal_plans()
        turns_df = load_turn_restrictions()
        _graph_instance = TrafficNetworkGraph().build(network_df, nodes_df, signal_df, turns_df)
    return _graph_instance


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    g = get_network_graph()
    print(f"Nodes: {len(g.G.nodes)}, Segments: {len(g.G.edges)}")

    # Test traversal
    test_seg = "R0001"
    print(f"\nTest segment: {test_seg}")
    print(f"  Upstream (depth=2): {g.get_upstream_segments(test_seg, 2)}")
    print(f"  Downstream (depth=2): {g.get_downstream_segments(test_seg, 2)}")
    print(f"  Neighbors: {g.get_neighboring_segments(test_seg)}")
    print(f"  Coords: {g.get_segment_coords(test_seg)}")

    bottlenecks = g.get_structural_bottlenecks()
    print(f"\nStructural bottlenecks ({len(bottlenecks)}): {bottlenecks[:5]}")

    # GeoJSON
    geojson = g.to_geojson()
    print(f"\nGeoJSON features: {len(geojson['features'])}")
    print("Done.")
