"""Self-contained HTML lineage report generation."""

from __future__ import annotations

import heapq
import json
from typing import Any

_NODE_WIDTH = 250
_NODE_HEIGHT = 68
_COLUMN_GAP = 370
_ROW_GAP = 108
_PADDING = 48
_CYCLE_MARGIN = 72


def _sort_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


def _compute_edge_ports(edges: list[dict[str, Any]]) -> list[dict[str, int]]:
    """Distribute source edges while converging incoming edges at one target."""
    ports = [
        {"source": _NODE_HEIGHT // 2, "target": _NODE_HEIGHT // 2}
        for _ in edges
    ]
    outgoing: dict[str, list[int]] = {}
    for index, edge in enumerate(edges):
        outgoing.setdefault(edge["source"], []).append(index)

    def assign(
        incident_edges: dict[str, list[int]],
        endpoint: str,
        peer_key: str,
    ) -> None:
        for indices in incident_edges.values():
            ordered = sorted(
                indices,
                key=lambda index: (
                    _sort_key(edges[index][peer_key]),
                    _sort_key(edges[index]["kind"]),
                    _sort_key(edges[index]["status"]),
                    _sort_key(edges[index].get("evidence_file", "")),
                    edges[index].get("line", 0),
                    edges[index].get("column", 0),
                ),
            )
            count = len(ordered)
            for rank, index in enumerate(ordered):
                if count == 1:
                    offset = _NODE_HEIGHT // 2
                else:
                    span = _NODE_HEIGHT - 24
                    offset = round(12 + rank * span / (count - 1))
                ports[index][endpoint] = offset
    assign(outgoing, "source", "target")
    assign(outgoing, "source", "target")
    return ports


def _compute_merge_groups(
    edges: list[dict[str, Any]],
    node_ids: set[str],
) -> list[dict[str, Any]]:
    """Group valid incoming edges so each target receives one arrowhead."""
    grouped: dict[str, list[int]] = {}
    for index, edge in enumerate(edges):
        if edge["source"] in node_ids and edge["target"] in node_ids:
            grouped.setdefault(edge["target"], []).append(index)
    return [
        {"target": target, "edgeIndices": grouped[target]}
        for target in sorted(grouped, key=_sort_key)
    ]


def _display_graph(
    graph: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Expand procedure-attributed data flows for visualization only."""
    objects = graph["objects"]
    edges = graph["edges"]
    object_ids = {item["id"] for item in objects}
    procedure_ids = {
        item["id"] for item in objects if item["type"] == "stored_procedure"
    }
    active_procedures = {
        edge.get("via_procedure")
        for edge in edges
        if edge["kind"] == "data_flow"
        and edge.get("via_procedure") in procedure_ids
    }
    for edge in edges:
        if edge["kind"] == "procedure_call":
            active_procedures.update(
                endpoint
                for endpoint in (edge["source"], edge["target"])
                if endpoint in procedure_ids
            )

    display_objects = [
        item
        for item in objects
        if item["type"] != "stored_procedure" or item["id"] in active_procedures
    ]
    display_ids = {item["id"] for item in display_objects}
    display_edges: list[dict[str, Any]] = []
    for edge in edges:
        via_procedure = edge.get("via_procedure")
        if (
            edge["kind"] == "data_flow"
            and via_procedure in active_procedures
            and edge["source"] in object_ids
            and edge["target"] in object_ids
        ):
            display_edges.extend(
                (
                    {
                        **edge,
                        "target": via_procedure,
                        "kind": "procedure_input",
                    },
                    {
                        **edge,
                        "source": via_procedure,
                        "kind": "procedure_output",
                    },
                )
            )
        elif edge["source"] in display_ids and edge["target"] in display_ids:
            display_edges.append(edge)

    return display_objects, display_edges


def _compute_layout(
    graph: dict[str, Any],
) -> tuple[dict[str, dict[str, int]], int, int]:
    """Assign stable left-to-right ranks, collapsing cycles into shared ranks."""
    objects = graph["objects"]
    edges = graph["edges"]
    node_ids = sorted((item["id"] for item in objects), key=_sort_key)
    if not node_ids:
        return {}, 600, 320

    adjacency = {node_id: set() for node_id in node_ids}
    reverse_adjacency = {node_id: set() for node_id in node_ids}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            reverse_adjacency[target].add(source)
    ordered_adjacency = {
        node_id: sorted(neighbors, key=_sort_key)
        for node_id, neighbors in adjacency.items()
    }
    ordered_reverse = {
        node_id: sorted(neighbors, key=_sort_key)
        for node_id, neighbors in reverse_adjacency.items()
    }

    visited: set[str] = set()
    finish_order: list[str] = []
    for start in node_ids:
        if start in visited:
            continue
        visited.add(start)
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            current, neighbor_index = stack[-1]
            neighbors = ordered_adjacency[current]
            if neighbor_index < len(neighbors):
                neighbor = neighbors[neighbor_index]
                stack[-1] = (current, neighbor_index + 1)
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append((neighbor, 0))
            else:
                finish_order.append(current)
                stack.pop()

    component_for: dict[str, int] = {}
    components: list[list[str]] = []
    for start in reversed(finish_order):
        if start in component_for:
            continue
        component_index = len(components)
        component: list[str] = []
        stack = [start]
        component_for[start] = component_index
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in reversed(ordered_reverse[current]):
                if neighbor not in component_for:
                    component_for[neighbor] = component_index
                    stack.append(neighbor)
        component.sort(key=_sort_key)
        components.append(component)

    component_edges = [set() for _ in components]
    indegree = [0 for _ in components]
    for source, targets in adjacency.items():
        source_component = component_for[source]
        for target in targets:
            target_component = component_for[target]
            if (
                source_component != target_component
                and target_component not in component_edges[source_component]
            ):
                component_edges[source_component].add(target_component)
                indegree[target_component] += 1

    ready = [index for index, count in enumerate(indegree) if count == 0]
    heapq.heapify(ready)
    component_rank = [0 for _ in components]
    while ready:
        current = heapq.heappop(ready)
        for target in sorted(component_edges[current]):
            component_rank[target] = max(
                component_rank[target], component_rank[current] + 1
            )
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, target)

    objects_by_id = {item["id"]: item for item in objects}
    layers: dict[int, list[str]] = {}
    for node_id in node_ids:
        layers.setdefault(component_rank[component_for[node_id]], []).append(node_id)
    for layer in layers.values():
        layer.sort(
            key=lambda node_id: (
                objects_by_id[node_id]["type"].casefold(),
                objects_by_id[node_id]["name"].casefold(),
                node_id.casefold(),
                node_id,
            )
        )

    positions: dict[str, dict[str, int]] = {}
    for rank in sorted(layers):
        for row, node_id in enumerate(layers[rank]):
            positions[node_id] = {
                "x": _PADDING + rank * _COLUMN_GAP,
                "y": _PADDING + row * _ROW_GAP,
                "rank": rank,
            }

    max_rank = max(layers)
    max_rows = max(len(layer) for layer in layers.values())
    width = _PADDING * 2 + max_rank * _COLUMN_GAP + _NODE_WIDTH + _CYCLE_MARGIN
    height = _PADDING * 2 + (max_rows - 1) * _ROW_GAP + _NODE_HEIGHT
    return positions, width, height


def _script_json(value: Any) -> str:
    """Serialize data safely inside a script element without closing it."""
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_html(graph: dict[str, Any]) -> str:
    """Render a deterministic, self-contained interactive lineage report."""
    display_objects, display_edges = _display_graph(graph)
    display_graph = {"objects": display_objects, "edges": display_edges}
    positions, width, height = _compute_layout(display_graph)
    payload = {
        "graph": graph,
        "displayObjects": display_objects,
        "displayEdges": display_edges,
        "layout": {"positions": positions, "width": width, "height": height},
        "edgePorts": _compute_edge_ports(display_edges),
        "mergeGroups": _compute_merge_groups(display_edges, set(positions)),
        "nodeWidth": _NODE_WIDTH,
        "nodeHeight": _NODE_HEIGHT,
    }
    data = _script_json(payload)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; object-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>Lightweight Lineage</title>
<style>
:root {{
  color-scheme: light;
  font-family: "Segoe UI", Arial, sans-serif;
  color: #172b4d;
  background: #f4f7fb;
  font-synthesis: none;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; min-width: 320px; min-height: 100vh; }}
button, input {{ font: inherit; }}
button {{ cursor: pointer; }}
.app-header {{
  display: flex; align-items: center; justify-content: space-between; gap: 20px;
  padding: 18px 24px; color: #fff; background: #102a43;
}}
.brand {{ display: flex; align-items: center; gap: 12px; }}
.brand-mark {{
  display: grid; width: 36px; height: 36px; place-items: center;
  border: 1px solid #6ea8fe; border-radius: 10px; color: #b8d5ff;
  font-weight: 800; font-size: 19px;
}}
h1 {{ margin: 0; font-size: 19px; letter-spacing: .01em; }}
.subtitle {{ margin-top: 3px; color: #c3d4e8; font-size: 12px; }}
.run-status {{ padding: 7px 11px; border: 1px solid #7694b5; border-radius: 999px; font-size: 12px; }}
.run-status[data-status="completed"] {{ color: #d3f9d8; border-color: #51b36a; }}
.run-status[data-status="completed_with_warnings"] {{ color: #ffecad; border-color: #d8a52a; }}
.run-status[data-status="completed_with_errors"] {{ color: #ffd1d1; border-color: #e16b6b; }}
.toolbar {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
  padding: 12px 24px; background: #fff; border-bottom: 1px solid #dce4ee;
}}
.search {{ display: flex; flex: 1 1 300px; gap: 8px; max-width: 620px; }}
.search input {{
  min-width: 120px; flex: 1; padding: 8px 11px; border: 1px solid #bac8d8;
  border-radius: 7px; color: #172b4d; background: #fff;
}}
.button {{
  padding: 8px 12px; border: 1px solid #b8c5d5; border-radius: 7px;
  color: #23415f; background: #fff;
}}
.button:hover {{ background: #f1f6fc; }}
.button-primary {{ border-color: #155eef; color: #fff; background: #155eef; }}
.button-primary:hover {{ background: #004eeb; }}
.stat {{ color: #52677e; font-size: 12px; white-space: nowrap; }}
.workspace {{
  display: grid; grid-template-columns: minmax(0, 1fr) 350px;
  height: calc(100vh - 132px); min-height: 420px;
}}
.graph-pane {{ min-width: 0; min-height: 0; overflow: auto; background-color: #f7f9fc; }}
.graph-scroll {{ width: max-content; min-width: 100%; min-height: 100%; padding: 14px; }}
.graph-svg {{ display: block; overflow: visible; }}
.empty-state {{
  display: grid; min-width: 420px; min-height: 280px; place-content: center;
  color: #60758b; text-align: center;
}}
.empty-state[hidden] {{ display: none; }}
.empty-state strong {{ margin-bottom: 8px; color: #334e68; font-size: 16px; }}
.edge {{ fill: none; stroke: #91a1b3; stroke-width: 1.8; opacity: .8; }}
.edge-inferred {{ stroke-dasharray: 7 5; }}
.edge-ambiguous {{ stroke: #c47b0b; stroke-dasharray: 4 4; }}
.edge-unknown_source, .edge-unknown_target {{ stroke: #c2413b; stroke-dasharray: 2 4; }}
.edge-procedure_input {{ stroke: #6b66a8; stroke-dasharray: 6 4; }}
.edge-procedure_output {{ stroke: #327d64; stroke-width: 2.4; }}
.edge-procedure_input.edge-inferred, .edge-procedure_output.edge-inferred {{ stroke-dasharray: 7 5; }}
.edge-procedure_input.edge-ambiguous, .edge-procedure_output.edge-ambiguous {{ stroke: #c47b0b; stroke-dasharray: 4 4; }}
.edge-procedure_input.edge-unknown_source, .edge-procedure_input.edge-unknown_target,
.edge-procedure_output.edge-unknown_source, .edge-procedure_output.edge-unknown_target {{ stroke: #c2413b; stroke-dasharray: 2 4; }}
.edge-merge {{ stroke: #71859a; stroke-width: 2.1; opacity: 1; }}
.edge.selected-route {{ stroke: #155eef; stroke-width: 3; opacity: 1; }}
.edge.dimmed {{ opacity: .12; }}
.node {{ cursor: pointer; outline: none; }}
.node rect {{ fill: #fff; stroke: #92a4b8; stroke-width: 1.5; rx: 9; }}
.node:hover rect, .node:focus rect {{ stroke: #155eef; stroke-width: 2.5; }}
.node.node-selected rect {{ fill: #eaf2ff; stroke: #155eef; stroke-width: 3; }}
.node.node-upstream rect {{ fill: #eef7ff; stroke: #3690d8; stroke-width: 2; }}
.node.node-downstream rect {{ fill: #effaf4; stroke: #36a269; stroke-width: 2; }}
.node.node-dimmed {{ opacity: .2; }}
.node.node-search-match rect {{ stroke: #d78a09; stroke-width: 3; }}
.node.node-unknown rect {{ fill: #fff8e8; stroke: #d08b11; }}
.node-type {{ fill: #60758b; font-size: 10px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }}
.node-name {{ fill: #172b4d; font-size: 13px; font-weight: 600; }}
.side-panel {{
  min-height: 0; overflow: auto; padding: 18px; border-left: 1px solid #dce4ee;
  background: #fff;
}}
.panel-section + .panel-section {{ margin-top: 22px; padding-top: 18px; border-top: 1px solid #e6ecf2; }}
h2 {{ margin: 0 0 12px; color: #243b53; font-size: 14px; }}
.placeholder {{ color: #73869a; font-size: 13px; line-height: 1.5; }}
.detail-name {{ margin: 0 0 6px; overflow-wrap: anywhere; color: #102a43; font-size: 17px; font-weight: 700; }}
.detail-meta {{ color: #60758b; font-size: 12px; line-height: 1.6; }}
.detail-id {{ display: block; margin-top: 8px; overflow-wrap: anywhere; color: #52677e; font: 11px Consolas, monospace; }}
.dependency-heading {{ margin: 14px 0 6px; color: #52677e; font-size: 12px; font-weight: 700; }}
.dependency-list, .diagnostic-list {{ display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }}
.dependency-button {{
  width: 100%; padding: 7px 8px; border: 1px solid #e2e9f1; border-radius: 6px;
  color: #24517a; background: #f8fafc; text-align: left; overflow-wrap: anywhere;
}}
.dependency-button:hover {{ border-color: #8db5e8; background: #edf5ff; }}
.diagnostic {{
  padding: 9px; border: 1px solid #e2e9f1; border-left-width: 3px;
  border-radius: 6px; background: #fbfcfe;
}}
.diagnostic[data-severity="error"] {{ border-left-color: #c2413b; }}
.diagnostic[data-severity="warning"] {{ border-left-color: #d08b11; }}
.diagnostic[data-severity="info"] {{ border-left-color: #3781b8; }}
.diagnostic-title {{ margin-bottom: 4px; color: #334e68; font-size: 12px; font-weight: 700; }}
.diagnostic-location {{ margin-bottom: 5px; color: #71859a; font-size: 11px; overflow-wrap: anywhere; }}
.diagnostic-message {{ color: #52677e; font-size: 12px; line-height: 1.45; overflow-wrap: anywhere; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px 14px; margin-left: auto; color: #60758b; font-size: 11px; }}
.legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
.legend-line {{ width: 23px; border-top: 2px solid #91a1b3; }}
.legend-line.inferred {{ border-top-style: dashed; }}
.legend-line.ambiguous {{ border-top: 2px dashed #c47b0b; }}
.legend-line.unknown {{ border-top: 2px dotted #c2413b; }}
.legend-line.procedure-input {{ border-top: 2px dashed #6b66a8; }}
.legend-line.procedure-output {{ border-top: 2px solid #327d64; }}
.legend-box {{ width: 12px; height: 12px; border: 1px solid #d08b11; border-radius: 3px; background: #fff8e8; }}
.footer-note {{ margin-top: 14px; color: #71859a; font-size: 11px; line-height: 1.5; }}
@media (max-width: 900px) {{
  .workspace {{ grid-template-columns: minmax(0, 1fr); height: auto; min-height: 0; }}
  .graph-pane {{ height: 62vh; min-height: 360px; }}
  .side-panel {{ max-height: 46vh; border-top: 1px solid #dce4ee; border-left: 0; }}
  .legend {{ margin-left: 0; }}
}}
@media (max-width: 540px) {{
  .app-header {{ padding: 14px; }}
  .toolbar {{ padding: 10px 14px; }}
  .search {{ flex-basis: 100%; }}
  .run-status {{ font-size: 10px; }}
}}
</style>
</head>
<body>
<header class="app-header">
  <div class="brand">
    <div class="brand-mark" aria-hidden="true">L</div>
    <div><h1>Lightweight Lineage</h1><div class="subtitle">Offline repository analysis</div></div>
  </div>
  <div id="run-status" class="run-status" role="status"></div>
</header>
<div class="toolbar">
  <form class="search" id="search-form">
    <input id="search-input" type="search" list="object-options" placeholder="Find an object by name or type..." aria-label="Find an object">
    <datalist id="object-options"></datalist>
    <button class="button button-primary" type="submit">Find</button>
  </form>
  <button class="button" id="clear-selection" type="button">Clear selection</button>
  <span class="stat" id="graph-stats"></span>
  <div class="legend" aria-label="Diagram legend">
    <span class="legend-item"><span class="legend-line"></span>Confirmed</span>
    <span class="legend-item"><span class="legend-line inferred"></span>Inferred</span>
    <span class="legend-item"><span class="legend-line ambiguous"></span>Ambiguous</span>
    <span class="legend-item"><span class="legend-line unknown"></span>Unknown endpoint</span>
    <span class="legend-item"><span class="legend-line procedure-input"></span>Procedure read/input</span>
    <span class="legend-item"><span class="legend-line procedure-output"></span>Procedure write/output</span>
    <span class="legend-item"><span class="legend-box"></span>Unresolved object</span>
  </div>
</div>
<main class="workspace">
  <section class="graph-pane" aria-label="Lineage graph">
    <div class="graph-scroll" id="graph-scroll">
      <div class="empty-state" id="empty-state" hidden>
        <div><strong>No lineage objects found</strong><br>The scan completed without discovering any permanent objects.</div>
      </div>
      <svg class="graph-svg" id="graph" role="group" aria-label="Directed lineage diagram"></svg>
    </div>
  </section>
  <aside class="side-panel">
    <section class="panel-section" aria-labelledby="details-heading">
      <h2 id="details-heading">Object details</h2>
      <div id="object-details" class="placeholder">Select an object to inspect its upstream and downstream dependencies.</div>
    </section>
    <section class="panel-section" aria-labelledby="diagnostics-heading">
      <h2 id="diagnostics-heading">Diagnostics</h2>
      <div id="diagnostics"></div>
    </section>
    <div class="footer-note">Select an object to highlight all connected upstream and downstream dependencies. The diagram and diagnostics are embedded in this file; no network access is required.</div>
  </aside>
</main>
<script id="lineage-data" type="application/json">{data}</script>
<script>
"use strict";
const payload = JSON.parse(document.getElementById("lineage-data").textContent);
const graph = payload.graph;
const displayObjects = payload.displayObjects;
const displayEdges = payload.displayEdges;
const positions = payload.layout.positions;
const edgePorts = payload.edgePorts;
const svg = document.getElementById("graph");
const objectDetails = document.getElementById("object-details");
const diagnosticsRoot = document.getElementById("diagnostics");
const nodeById = new Map(displayObjects.map((item) => [item.id, item]));
const outgoing = new Map(displayObjects.map((item) => [item.id, []]));
const incoming = new Map(displayObjects.map((item) => [item.id, []]));
for (const edge of displayEdges) {{
  if (outgoing.has(edge.source) && incoming.has(edge.target)) {{
    outgoing.get(edge.source).push(edge);
    incoming.get(edge.target).push(edge);
  }}
}}
for (const edges of [...outgoing.values(), ...incoming.values()]) {{
  edges.sort((a, b) => compareText(a.target, b.target) || compareText(a.source, b.source) || compareText(a.kind, b.kind));
}}
const nodeElements = new Map();
const edgeElements = [];
const mergeElements = [];
let selectedId = null;
let searchTerm = "";
const arrowClearance = 4;
const mergeOffset = 20;
const cycleRouteY = 24;

function compareText(left, right) {{
  const first = String(left).toLowerCase();
  const second = String(right).toLowerCase();
  return first < second ? -1 : first > second ? 1 : String(left) < String(right) ? -1 : String(left) > String(right) ? 1 : 0;
}}
function svgElement(tag, attributes = {{}}) {{
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  return element;
}}
function displayType(value) {{ return String(value || "object").replace(/_/g, " "); }}
function edgeClass(edge) {{
  return "edge edge-" + String(edge.status || "confirmed").replace(/[^a-z0-9_-]/gi, "-") +
    " edge-" + String(edge.kind || "data_flow").replace(/[^a-z0-9_-]/gi, "-");
}}
function edgeDescription(edge) {{
  if (edge.kind === "procedure_input") return `Read by procedure: ${{edge.source}} → ${{edge.target}}`;
  if (edge.kind === "procedure_output") return `Written by procedure: ${{edge.source}} → ${{edge.target}}`;
  return `${{edge.kind}}: ${{edge.source}} → ${{edge.target}}`;
}}
function makeEdgePath(edge, edgeIndex) {{
  const source = positions[edge.source];
  const target = positions[edge.target];
  const sourceY = source.y + edgePorts[edgeIndex].source;
  const targetY = target.y + payload.nodeHeight / 2;
  if (source.rank < target.rank) {{
    const startX = source.x + payload.nodeWidth;
    const junctionX = target.x - mergeOffset;
    const controlX = (startX + junctionX) / 2;
    return `M ${{startX}} ${{sourceY}} C ${{controlX}} ${{sourceY}}, ${{controlX}} ${{targetY}}, ${{junctionX}} ${{targetY}}`;
  }}
  const startX = source.x + payload.nodeWidth;
  const outerX = startX + 58;
  const approachX = Math.max(8, target.x - 58);
  const junctionX = target.x - mergeOffset;
  return `M ${{startX}} ${{sourceY}} C ${{outerX}} ${{sourceY}}, ${{outerX}} ${{cycleRouteY}}, ${{outerX}} ${{cycleRouteY}} L ${{approachX}} ${{cycleRouteY}} C ${{approachX}} ${{targetY}}, ${{junctionX}} ${{targetY}}, ${{junctionX}} ${{targetY}}`;
}}
function renderGraph() {{
  svg.setAttribute("width", String(payload.layout.width));
  svg.setAttribute("height", String(payload.layout.height));
  svg.setAttribute("viewBox", `0 0 ${{payload.layout.width}} ${{payload.layout.height}}`);
  const defs = svgElement("defs");
  const marker = svgElement("marker", {{
    id: "arrowhead", markerWidth: "10", markerHeight: "10", refX: "10", refY: "5",
    orient: "auto", markerUnits: "userSpaceOnUse"
  }});
  marker.append(svgElement("path", {{d: "M 0 0 L 10 5 L 0 10 z", fill: "#71859a"}}));
  defs.append(marker);
  svg.append(defs);
  const edgeLayer = svgElement("g", {{ "aria-label": "Relationships" }});
  for (const [edgeIndex, edge] of displayEdges.entries()) {{
    if (!positions[edge.source] || !positions[edge.target]) continue;
    const path = svgElement("path", {{
      d: makeEdgePath(edge, edgeIndex), class: edgeClass(edge),
      "data-source": edge.source, "data-target": edge.target
    }});
    const title = svgElement("title");
    title.textContent = `${{edgeDescription(edge)}} (${{edge.status}}) — ${{edge.evidence_file}}:${{edge.line}}`;
    path.append(title);
    edgeLayer.append(path);
    edgeElements.push({{element: path, edge}});
  }}
  svg.append(edgeLayer);
  const mergeLayer = svgElement("g", {{ "aria-label": "Converged relationship arrows" }});
  for (const group of payload.mergeGroups) {{
    const target = positions[group.target];
    const centerY = target.y + payload.nodeHeight / 2;
    const junctionX = target.x - mergeOffset;
    const arrowX = target.x - arrowClearance;
    const edges = group.edgeIndices.map((index) => displayEdges[index]);
    const path = svgElement("path", {{
      d: `M ${{junctionX}} ${{centerY}} L ${{arrowX}} ${{centerY}}`,
      class: "edge edge-merge",
      "marker-end": "url(#arrowhead)",
      "data-merge-target": group.target
    }});
    const title = svgElement("title");
    const count = edges.length;
    title.textContent = `${{count}} relationship${{count === 1 ? "" : "s"}} ${{count === 1 ? "converges" : "converge"}} on ${{nodeById.get(group.target).name}}`;
    path.append(title);
    mergeLayer.append(path);
    mergeElements.push({{element: path, edges}});
  }}
  svg.append(mergeLayer);
  const nodeLayer = svgElement("g", {{ "aria-label": "Objects" }});
  const orderedObjects = [...displayObjects].sort((a, b) =>
    positions[a.id].rank - positions[b.id].rank ||
    positions[a.id].y - positions[b.id].y ||
    compareText(a.id, b.id)
  );
  for (const object of orderedObjects) {{
    const point = positions[object.id];
    const group = svgElement("g", {{
      class: "node" + (object.type === "unknown" ? " node-unknown" : ""),
      transform: `translate(${{point.x}} ${{point.y}})`,
      tabindex: "0", role: "button",
      "aria-label": `${{object.name}}, ${{displayType(object.type)}}, ${{object.status}}`
    }});
    group.append(svgElement("rect", {{width: payload.nodeWidth, height: payload.nodeHeight}}));
    const typeLabel = svgElement("text", {{x: "13", y: "21", class: "node-type"}});
    typeLabel.textContent = displayType(object.type);
    group.append(typeLabel);
    const nameLabel = svgElement("text", {{x: "13", y: "46", class: "node-name"}});
    const visibleName = object.name.length > 33 ? object.name.slice(0, 30) + "..." : object.name;
    nameLabel.textContent = visibleName;
    group.append(nameLabel);
    const title = svgElement("title");
    title.textContent = `${{object.name}} (${{object.id}}) — ${{object.status}}`;
    group.append(title);
    group.addEventListener("click", () => selectObject(object.id, true));
    group.addEventListener("keydown", (event) => {{
      if (event.key === "Enter" || event.key === " ") {{
        event.preventDefault();
        selectObject(object.id, true);
      }}
    }});
    nodeLayer.append(group);
    nodeElements.set(object.id, group);
  }}
  svg.append(nodeLayer);
  document.getElementById("empty-state").hidden = displayObjects.length !== 0;
  svg.hidden = displayObjects.length === 0;
}}
function reachable(startId, direction) {{
  const adjacency = direction === "upstream" ? incoming : outgoing;
  const found = new Set();
  const pending = [startId];
  while (pending.length) {{
    const current = pending.pop();
    for (const edge of adjacency.get(current) || []) {{
      const neighbor = direction === "upstream" ? edge.source : edge.target;
      if (neighbor !== startId && !found.has(neighbor)) {{
        found.add(neighbor);
        pending.push(neighbor);
      }}
    }}
  }}
  return found;
}}
function appendDependencyList(parent, heading, ids) {{
  const title = document.createElement("div");
  title.className = "dependency-heading";
  title.textContent = `${{heading}} (${{ids.length}})`;
  parent.append(title);
  if (!ids.length) {{
    const empty = document.createElement("div");
    empty.className = "placeholder";
    empty.textContent = "None";
    parent.append(empty);
    return;
  }}
  const list = document.createElement("ul");
  list.className = "dependency-list";
  for (const id of ids) {{
    const object = nodeById.get(id);
    if (!object) continue;
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dependency-button";
    button.textContent = `${{object.name}} · ${{displayType(object.type)}}`;
    button.addEventListener("click", () => selectObject(id, true));
    item.append(button);
    list.append(item);
  }}
  parent.append(list);
}}
function updateDetails() {{
  objectDetails.replaceChildren();
  const object = nodeById.get(selectedId);
  if (!object) {{
    objectDetails.className = "placeholder";
    objectDetails.textContent = "Select an object to inspect its upstream and downstream dependencies.";
    return;
  }}
  objectDetails.className = "";
  const name = document.createElement("div");
  name.className = "detail-name";
  name.textContent = object.name;
  objectDetails.append(name);
  const meta = document.createElement("div");
  meta.className = "detail-meta";
  meta.textContent = `${{displayType(object.type)}} · ${{object.status}}` +
    (object.parse_status ? ` · SQL ${{object.parse_status}}` : "");
  objectDetails.append(meta);
  const id = document.createElement("code");
  id.className = "detail-id";
  id.textContent = object.id;
  objectDetails.append(id);
  if (object.source_file) {{
    const source = document.createElement("div");
    source.className = "detail-meta";
    source.textContent = `Defined in ${{object.source_file}}`;
    objectDetails.append(source);
  }}
  if (object.referenced_in && object.referenced_in.length) {{
    const referenced = document.createElement("div");
    referenced.className = "detail-meta";
    referenced.textContent = `Referenced in: ${{object.referenced_in.join(", ")}}`;
    objectDetails.append(referenced);
  }}
  const upstream = reachable(selectedId, "upstream");
  const downstream = reachable(selectedId, "downstream");
  const orderIds = (ids) => [...ids].sort((a, b) =>
    compareText(nodeById.get(a).name, nodeById.get(b).name) || compareText(a, b)
  );
  appendDependencyList(objectDetails, "Upstream dependencies", orderIds(upstream));
  appendDependencyList(objectDetails, "Downstream dependencies", orderIds(downstream));
}}
function updateHighlights() {{
  const upstream = selectedId ? reachable(selectedId, "upstream") : new Set();
  const downstream = selectedId ? reachable(selectedId, "downstream") : new Set();
  const routeEdges = new Set();
  for (const id of upstream) for (const edge of outgoing.get(id) || []) {{
    if (upstream.has(edge.target) || edge.target === selectedId) routeEdges.add(edge);
  }}
  for (const id of downstream) for (const edge of outgoing.get(id) || []) {{
    if (downstream.has(edge.target) || edge.target === selectedId) routeEdges.add(edge);
  }}
  for (const edge of outgoing.get(selectedId) || []) {{
    if (downstream.has(edge.target)) routeEdges.add(edge);
  }}
  for (const [id, element] of nodeElements) {{
    element.classList.toggle("node-selected", id === selectedId);
    element.classList.toggle("node-upstream", upstream.has(id));
    element.classList.toggle("node-downstream", downstream.has(id));
    element.classList.toggle("node-dimmed", Boolean(selectedId) && id !== selectedId && !upstream.has(id) && !downstream.has(id));
    const searchMatch = searchTerm && (nodeById.get(id).name + " " + nodeById.get(id).type).toLocaleLowerCase().includes(searchTerm);
    element.classList.toggle("node-search-match", Boolean(searchMatch));
    if (searchTerm) element.classList.toggle("node-dimmed", !searchMatch && id !== selectedId && !upstream.has(id) && !downstream.has(id));
  }}
  for (const {{element, edge}} of edgeElements) {{
    const isRoute = routeEdges.has(edge);
    element.classList.toggle("selected-route", isRoute);
    element.classList.toggle("dimmed", Boolean(selectedId) && !isRoute);
  }}
  for (const {{element, edges}} of mergeElements) {{
    const isRoute = edges.some((edge) => routeEdges.has(edge));
    element.classList.toggle("selected-route", isRoute);
    element.classList.toggle("dimmed", Boolean(selectedId) && !isRoute);
  }}
}}
function selectObject(id, scrollIntoView) {{
  if (!nodeById.has(id)) return;
  selectedId = id;
  updateDetails();
  updateHighlights();
  if (scrollIntoView) nodeElements.get(id).scrollIntoView({{block: "center", inline: "center"}});
}}
function renderDiagnostics() {{
  const status = document.getElementById("run-status");
  status.dataset.status = graph.run_status;
  status.textContent = displayType(graph.run_status).replace(/^./, (letter) => letter.toUpperCase());
  document.getElementById("graph-stats").textContent =
    `${{displayObjects.length}} objects · ${{displayEdges.length}} relationships · ${{graph.diagnostics.length}} diagnostics`;
  const diagnostics = [...graph.diagnostics].sort((a, b) =>
    compareText(a.file || "", b.file || "") ||
    (a.line || 0) - (b.line || 0) ||
    compareText(a.code || "", b.code || "")
  );
  if (!diagnostics.length) {{
    const empty = document.createElement("div");
    empty.className = "placeholder";
    empty.textContent = "No warnings or errors.";
    diagnosticsRoot.append(empty);
    return;
  }}
  const list = document.createElement("ul");
  list.className = "diagnostic-list";
  for (const diagnostic of diagnostics) {{
    const item = document.createElement("li");
    item.className = "diagnostic";
    item.dataset.severity = diagnostic.severity || "info";
    const title = document.createElement("div");
    title.className = "diagnostic-title";
    title.textContent = `${{displayType(diagnostic.severity)}} · ${{displayType(diagnostic.code)}}`;
    const location = document.createElement("div");
    location.className = "diagnostic-location";
    location.textContent = `${{diagnostic.file || "Unknown file"}}` +
      (diagnostic.line ? `:${{diagnostic.line}}` : "") +
      (diagnostic.column ? `:${{diagnostic.column}}` : "");
    const message = document.createElement("div");
    message.className = "diagnostic-message";
    message.textContent = diagnostic.message || "";
    item.append(title, location, message);
    list.append(item);
  }}
  diagnosticsRoot.append(list);
}}
renderGraph();
renderDiagnostics();
document.getElementById("search-form").addEventListener("submit", (event) => {{
  event.preventDefault();
  const input = document.getElementById("search-input");
  searchTerm = input.value.trim().toLocaleLowerCase();
  updateHighlights();
  if (!searchTerm) return;
  const match = displayObjects.find((object) =>
    (object.name + " " + object.type).toLocaleLowerCase().includes(searchTerm)
  );
  if (match) selectObject(match.id, true);
}});
document.getElementById("search-input").addEventListener("input", (event) => {{
  searchTerm = event.target.value.trim().toLocaleLowerCase();
  updateHighlights();
}});
document.getElementById("clear-selection").addEventListener("click", () => {{
  selectedId = null;
  updateDetails();
  updateHighlights();
}});
const options = document.getElementById("object-options");
for (const object of displayObjects) {{
  const option = document.createElement("option");
  option.value = object.name;
  option.label = displayType(object.type);
  options.append(option);
}}
</script>
</body>
</html>
"""


__all__ = ["render_html"]
