"""Inductive Miner discovery + BPMN 2.0 export (Story 2.2).

PM4Py's Inductive Miner yields a *sound* process model. We expose it two ways:

* :func:`export_bpmn` serializes the discovered model to BPMN 2.0 XML. We compute
  a layered left-to-right layout ourselves (coordinates + edge waypoints) instead
  of invoking PM4Py's graphviz layouter, so the export stays dependency-free and
  works headless/in CI **and** opens cleanly in any BPMN modeler (bpmn.io,
  Camunda Modeler) rather than stacking every shape at the origin.
* :func:`discover_inductive_graph` projects the BPMN model onto the same
  ``ProcessGraph`` shape the frontend canvas already renders, so the UI can
  toggle between Heuristic and Inductive results. Edges connect tasks that are
  reachable through gateways/silent steps in the sound model; frequencies and
  durations are measured from the actual event stream.
"""

from __future__ import annotations

from collections import defaultdict

import pm4py
from pm4py.objects.bpmn.exporter.variants import etree as bpmn_etree
from pm4py.objects.bpmn.obj import BPMN
from sqlalchemy.orm import Session

from app.schemas.discovery import ActivityNode, ProcessEdge, ProcessGraph
from app.services.process_data import load_dataframe, load_traces

# Layout geometry (BPMN diagram units / pixels).
_COL_SPACING = 180
_ROW_SPACING = 100
_MARGIN = 40


def _discover_bpmn(db: Session, log_id: str) -> BPMN:
    df = load_dataframe(db, log_id)
    if df.empty:
        return BPMN()
    return pm4py.discover_bpmn_inductive(df)


def _node_size(node: BPMN.BPMNNode) -> tuple[int, int]:
    if isinstance(node, BPMN.Gateway):
        return 50, 50
    if isinstance(node, BPMN.Event):
        return 36, 36
    return 100, 60


def _rank_nodes(
    nodes: list[BPMN.BPMNNode],
    out_adj: dict[BPMN.BPMNNode, list[BPMN.BPMNNode]],
) -> dict[BPMN.BPMNNode, int]:
    """Longest-path layering (rank = longest chain from a source).

    Start events / nodes without predecessors seed rank 0. Edges are relaxed up
    to ``len(nodes)`` times so the result is stable even when the sound model
    contains loops (cycle edges are simply truncated at the cap).
    """
    rank: dict[BPMN.BPMNNode, int] = {n: 0 for n in nodes}
    for _ in range(max(len(nodes), 1)):
        changed = False
        for src, targets in out_adj.items():
            for tgt in targets:
                if rank[tgt] < rank[src] + 1:
                    rank[tgt] = rank[src] + 1
                    changed = True
        if not changed:
            break
    return rank


def _layout_bpmn(bpmn: BPMN) -> BPMN:
    """Assign coordinates and edge waypoints in-place so the export is usable.

    Without this every shape exports at ``x=0 y=0`` and modelers render the
    diagram as a single pile of overlapping elements.
    """
    nodes = list(bpmn.get_nodes())
    if not nodes:
        return bpmn

    out_adj: dict[BPMN.BPMNNode, list[BPMN.BPMNNode]] = defaultdict(list)
    for flow in bpmn.get_flows():
        out_adj[flow.get_source()].append(flow.get_target())

    rank = _rank_nodes(nodes, out_adj)

    by_rank: dict[int, list[BPMN.BPMNNode]] = defaultdict(list)
    for node in nodes:  # preserve discovery order within a rank for stability
        by_rank[rank[node]].append(node)

    layout = bpmn.get_layout()
    bounds: dict[BPMN.BPMNNode, tuple[int, int, int, int]] = {}
    tallest = _max_col_height(by_rank)

    for r in sorted(by_rank):
        column = by_rank[r]
        col_height = sum(_node_size(n)[1] for n in column) + _ROW_SPACING * (
            len(column) - 1
        )
        x = _MARGIN + r * _COL_SPACING
        # center each column vertically around the tallest column's mid-line
        y = _MARGIN + max((tallest - col_height) // 2, 0)
        for node in column:
            w, h = _node_size(node)
            nl = layout.get(node)
            nl.set_x(x)
            nl.set_y(y)
            nl.set_width(w)
            nl.set_height(h)
            bounds[node] = (x, y, w, h)
            y += h + _ROW_SPACING

    for flow in bpmn.get_flows():
        src_b = bounds.get(flow.get_source())
        tgt_b = bounds.get(flow.get_target())
        if src_b is None or tgt_b is None:
            continue
        sx, sy, sw, sh = src_b
        tx, ty, _tw, th = tgt_b
        fl = layout.get(flow)
        fl.del_waypoints()
        fl.add_waypoint((sx + sw, sy + sh // 2))
        fl.add_waypoint((tx, ty + th // 2))

    return bpmn


def _max_col_height(by_rank: dict[int, list[BPMN.BPMNNode]]) -> int:
    heights = []
    for column in by_rank.values():
        heights.append(
            sum(_node_size(n)[1] for n in column) + _ROW_SPACING * (len(column) - 1)
        )
    return max(heights, default=0)


def export_bpmn(db: Session, log_id: str) -> str:
    """Return valid, laid-out BPMN 2.0 XML for the inductively-mined model."""
    bpmn = _layout_bpmn(_discover_bpmn(db, log_id))
    xml = bpmn_etree.get_xml_string(bpmn)
    return xml.decode("utf-8") if isinstance(xml, bytes) else xml


def _is_task(node: BPMN.BPMNNode) -> bool:
    return isinstance(node, BPMN.Task) and bool(node.get_name())


def _model_edges(bpmn: BPMN) -> set[tuple[str, str]]:
    """Task-to-task edges, collapsing gateways and silent/non-task nodes."""
    out_adj: dict[BPMN.BPMNNode, list[BPMN.BPMNNode]] = defaultdict(list)
    for flow in bpmn.get_flows():
        out_adj[flow.get_source()].append(flow.get_target())

    def reachable_tasks(start: BPMN.BPMNNode) -> set[str]:
        seen: set[BPMN.BPMNNode] = set()
        found: set[str] = set()
        stack = list(out_adj.get(start, []))
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            if _is_task(node):
                found.add(node.get_name())
            else:
                stack.extend(out_adj.get(node, []))
        return found

    edges: set[tuple[str, str]] = set()
    for node in bpmn.get_nodes():
        if _is_task(node):
            for target in reachable_tasks(node):
                edges.add((node.get_name(), target))
    return edges


def discover_inductive_graph(db: Session, log_id: str) -> ProcessGraph:
    bpmn = _discover_bpmn(db, log_id)
    model_edges = _model_edges(bpmn)
    traces = list(load_traces(db, log_id).values())

    activity_freq: dict[str, int] = defaultdict(int)
    df_count: dict[tuple[str, str], int] = defaultdict(int)
    df_duration: dict[tuple[str, str], float] = defaultdict(float)
    start_freq: dict[str, int] = defaultdict(int)
    end_freq: dict[str, int] = defaultdict(int)

    for trace in traces:
        if not trace:
            continue
        start_freq[trace[0][0]] += 1
        end_freq[trace[-1][0]] += 1
        for act, _ts in trace:
            activity_freq[act] += 1
        for (a_act, a_ts), (b_act, b_ts) in zip(trace, trace[1:], strict=False):
            pair = (a_act, b_act)
            df_count[pair] += 1
            df_duration[pair] += max((b_ts - a_ts).total_seconds(), 0.0)

    edges = [
        ProcessEdge(
            source=a,
            target=b,
            frequency=df_count.get((a, b), 0),
            dependency=1.0,
            avg_duration_seconds=(
                round(df_duration[(a, b)] / df_count[(a, b)], 2)
                if df_count.get((a, b))
                else 0.0
            ),
        )
        for (a, b) in sorted(model_edges)
    ]

    nodes = [
        ActivityNode(
            id=act,
            label=act,
            frequency=activity_freq[act],
            is_start=act in start_freq,
            is_end=act in end_freq,
            avg_duration_seconds=_avg_outgoing_duration(act, edges),
        )
        for act in sorted(activity_freq)
    ]

    return ProcessGraph(
        log_id=log_id,
        algorithm="inductive",
        nodes=nodes,
        edges=edges,
        case_count=len(traces),
        event_count=sum(activity_freq.values()),
        start_activities=sorted(start_freq),
        end_activities=sorted(end_freq),
        dependency_threshold=0.0,
        frequency_threshold=1,
    )


def _avg_outgoing_duration(act: str, edges: list[ProcessEdge]) -> float | None:
    out = [e for e in edges if e.source == act and e.frequency > 0]
    total_w = sum(e.frequency for e in out)
    if total_w == 0:
        return None
    return round(sum(e.avg_duration_seconds * e.frequency for e in out) / total_w, 2)
