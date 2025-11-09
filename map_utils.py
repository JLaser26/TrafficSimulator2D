#!/usr/bin/env python3
# map_utils.py
# Geometric road graph builder: roads -> nodes placed on rectangles and intersections
# Nodes are strings for road points and ints for hub ids (keeps compatibility).
# Exposes: load_map_data(path), build_graph(mapdata), find_path(edges, start_id, goal_id, traffic_counts=None)

import math
import json
import heapq
from collections import defaultdict

def load_map_data(path):
    with open(path, 'r') as f:
        return json.load(f)

def _rect_overlap(a, b):
    """Return overlap rect (x,y,w,h) between rect a and b or None if no overlap.
    rect format: {'x','y','w','h'} (axis aligned)
    """
    x1 = max(a['x'], b['x'])
    y1 = max(a['y'], b['y'])
    x2 = min(a['x'] + a['w'], b['x'] + b['w'])
    y2 = min(a['y'] + a['h'], b['y'] + b['h'])
    if x2 > x1 and y2 > y1:
        return {'x': x1, 'y': y1, 'w': (x2 - x1), 'h': (y2 - y1)}
    return None

def _mid(pt):
    return (pt[0] + pt[1]) / 2.0

def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

def build_graph(mapdata, hub_snap_dist=80):
    """
    Build a graph where:
      - each road rectangle produces several nodes: endpoints (along its long axis) + mid
      - intersections between rectangles create intersection nodes
      - nodes on the same road are connected in order (so edges follow the road)
      - hubs are connected to nearest road node if within hub_snap_dist
    Returns: nodes: {node_id: (x,y)}, edges: {node_id: [(neighbor_id, distance), ...]}
    node_id: strings for road-derived nodes (e.g., "r5_left"), integers for hub ids (keeps compatibility)
    """
    roads = mapdata.get('roads', [])
    hubs = mapdata.get('hubs', [])
    symbols = mapdata.get('symbols', [])

    nodes = {}     # node_id -> (x,y)
    node_roads = defaultdict(list)  # node_id -> list of road ids it belongs to
    edges = defaultdict(list)

    # 1) Create primary nodes for each road: left/top, mid, right/bottom depending on orientation
    for r in roads:
        rid = r['id']
        x, y, w, h = r['x'], r['y'], r['w'], r['h']
        cx = x + w / 2.0
        cy = y + h / 2.0

        # Decide orientation: treat as horizontal if width >= height, else vertical
        if w >= h:
            # horizontal road: create left, mid, right (use centers along centerline)
            left = (x, cy)
            mid = (cx, cy)
            right = (x + w, cy)
            nodes[f"r{rid}_L"] = left
            nodes[f"r{rid}_M"] = mid
            nodes[f"r{rid}_R"] = right
            node_roads[f"r{rid}_L"].append(rid)
            node_roads[f"r{rid}_M"].append(rid)
            node_roads[f"r{rid}_R"].append(rid)
            # connect along road (L <-> M <-> R)
            dLM = _dist(left, mid)
            dMR = _dist(mid, right)
            edges[f"r{rid}_L"].append((f"r{rid}_M", dLM))
            edges[f"r{rid}_M"].append((f"r{rid}_L", dLM))
            edges[f"r{rid}_M"].append((f"r{rid}_R", dMR))
            edges[f"r{rid}_R"].append((f"r{rid}_M", dMR))
        else:
            # vertical road: top, mid, bottom
            top = (cx, y)
            mid = (cx, cy)
            bottom = (cx, y + h)
            nodes[f"r{rid}_T"] = top
            nodes[f"r{rid}_M"] = mid
            nodes[f"r{rid}_B"] = bottom
            node_roads[f"r{rid}_T"].append(rid)
            node_roads[f"r{rid}_M"].append(rid)
            node_roads[f"r{rid}_B"].append(rid)
            dTM = _dist(top, mid)
            dMB = _dist(mid, bottom)
            edges[f"r{rid}_T"].append((f"r{rid}_M", dTM))
            edges[f"r{rid}_M"].append((f"r{rid}_T", dTM))
            edges[f"r{rid}_M"].append((f"r{rid}_B", dMB))
            edges[f"r{rid}_B"].append((f"r{rid}_M", dMB))

    # 2) Detect rectangle intersections and create nodes at their overlap centers
    #    also link intersection nodes to the road nodes of both roads
    for i in range(len(roads)):
        for j in range(i + 1, len(roads)):
            a = roads[i]
            b = roads[j]
            ov = _rect_overlap(a, b)
            if ov:
                # intersection center
                ix = ov['x'] + ov['w'] / 2.0
                iy = ov['y'] + ov['h'] / 2.0
                inter_id = f"i{a['id']}_{b['id']}"
                nodes[inter_id] = (ix, iy)
                node_roads[inter_id].append(a['id'])
                node_roads[inter_id].append(b['id'])
                # Connect intersection to the nearest nodes on each road (which we created earlier)
                # Find road-node ids that belong to road a and road b
                road_a_nodes = [nid for nid in nodes.keys() if nid.startswith(f"r{a['id']}_")]
                road_b_nodes = [nid for nid in nodes.keys() if nid.startswith(f"r{b['id']}_")]
                # connect to closest from each list
                best_a = None; best_da = float('inf')
                for nid in road_a_nodes:
                    d = _dist(nodes[nid], (ix, iy))
                    if d < best_da:
                        best_da = d; best_a = nid
                best_b = None; best_db = float('inf')
                for nid in road_b_nodes:
                    d = _dist(nodes[nid], (ix, iy))
                    if d < best_db:
                        best_db = d; best_b = nid
                if best_a:
                    edges[inter_id].append((best_a, best_da))
                    edges[best_a].append((inter_id, best_da))
                if best_b:
                    edges[inter_id].append((best_b, best_db))
                    edges[best_b].append((inter_id, best_db))

    # 3) Connect road endpoints across short gaps: if two road nodes are very close (touching),
    #    create an edge. This helps when a road's L/M/R may be close to another road's node.
    all_node_ids = list(nodes.keys())
    for i in range(len(all_node_ids)):
        for j in range(i + 1, len(all_node_ids)):
            n1 = all_node_ids[i]
            n2 = all_node_ids[j]
            # skip if already connected
            already = any(nb == n2 for nb, _ in edges.get(n1, []))
            if already:
                continue
            d = _dist(nodes[n1], nodes[n2])
            # threshold: if nodes are physically very close (e.g., share corner/intersection)
            if d < 40.0:
                edges[n1].append((n2, d))
                edges[n2].append((n1, d))

    # 4) Hubs: add hub ids (integers) as nodes and connect to nearest road node (snap)
    for h in hubs:
        hid = h['id']  # integer id
        hx, hy = h['x'], h['y']
        nodes[hid] = (hx, hy)
        edges[hid] = []
        # find nearest road-derived node
        best = None; bd = float('inf')
        for nid, (nx, ny) in nodes.items():
            if nid == hid:
                continue
            # prefer road nodes (strings starting with 'r' or 'i') over other hubs
            d = _dist((hx, hy), (nx, ny))
            if d < bd:
                bd = d; best = nid
        # connect if within snap distance
        if best is not None and bd <= hub_snap_dist:
            edges[hid].append((best, bd))
            edges[best].append((hid, bd))
        # otherwise still keep hub isolated (simulator won't spawn until connected)

    # Done
    return nodes, dict(edges)


def find_path(edges, start_id, goal_id, traffic_counts=None):
    """
    Dijkstra pathfinder on the constructed graph.
    edges: dict node -> list of (neighbor, weight)
    nodes are opaque ids (strings or ints)
    returns: list of node ids from start to goal (inclusive) or None if unreachable
    """
    if start_id not in edges or goal_id not in edges:
        return None
    if traffic_counts is None:
        traffic_counts = {}

    pq = [(0.0, start_id, [start_id])]
    seen = {}

    while pq:
        cost, node, path = heapq.heappop(pq)
        if node == goal_id:
            return path
        if node in seen and seen[node] <= cost:
            continue
        seen[node] = cost
        for nbr, w in edges.get(node, []):
            key = tuple(sorted((str(node), str(nbr))))
            t = traffic_counts.get(key, 0)
            nc = cost + w + t * 10.0
            if nbr not in seen or nc < seen.get(nbr, float('inf')):
                heapq.heappush(pq, (nc, nbr, path + [nbr]))
    return None
