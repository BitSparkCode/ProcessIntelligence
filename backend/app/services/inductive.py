"""Inductive Miner discovery + BPMN 2.0 export (Story 2.2).

PM4Py's Inductive Miner yields a *sound* process model. We expose it two ways:

* :func:`export_bpmn` serializes the discovered model to BPMN 2.0 XML (without
  invoking the graphviz layouter, so it works in headless/CI environments).
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


def _discover_bpmn(db: Session, log_id: str) -> BPMN:
    df = load_dataframe(db, log_id)
    if df.empty:
        return BPMN()
    return pm4py.discover_bpmn_inductive(df)


def export_bpmn(db: Session, log_id: str) -> str:
    """Return valid BPMN 2.0 XML for the inductively-mined model."""
    bpmn = _discover_bpmn(db, log_id)
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
