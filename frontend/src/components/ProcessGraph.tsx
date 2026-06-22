import { useCallback, useEffect, useMemo, useState } from "react";
import dagre from "dagre";
import {
  Background,
  BackgroundVariant,
  Controls,
  type Edge,
  MarkerType,
  MiniMap,
  type Node,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  type BottleneckReport,
  type DiscoveryParams,
  discoverHeuristicMiner,
  discoverInductiveMiner,
  downloadBpmn,
  type ProcessGraph as ProcessGraphData,
  type Variant,
} from "../api";
import ActivityNodeCard, { type ActivityCardData } from "./ActivityNodeCard";
import VariantsPanel from "./VariantsPanel";
import PerformancePanel from "./PerformancePanel";
import BottlenecksPanel from "./BottlenecksPanel";
import ConformancePanel from "./ConformancePanel";
import { formatDuration } from "../format";

const nodeTypes = { activity: ActivityNodeCard };

type EdgeColorMode = "frequency" | "time";
type Algorithm = "heuristic" | "inductive";
type SidePanel = "variants" | "performance" | "bottlenecks" | "conformance" | null;

function pathEdgeIds(sequence: string[]): Set<string> {
  const ids = new Set<string>();
  for (let i = 0; i + 1 < sequence.length; i++) {
    ids.add(`${sequence[i]}->${sequence[i + 1]}`);
  }
  return ids;
}

const NODE_W = 200;
const NODE_H = 96;

function layout(graph: ProcessGraphData): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 50, ranksep: 90 });
  g.setDefaultEdgeLabel(() => ({}));

  graph.nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  graph.edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  const maxFrequency = Math.max(1, ...graph.nodes.map((n) => n.frequency));

  const nodes: Node[] = graph.nodes.map((n) => {
    const pos = g.node(n.id);
    const data: ActivityCardData = {
      label: n.label,
      frequency: n.frequency,
      maxFrequency,
      isStart: n.is_start,
      isEnd: n.is_end,
      avgDurationSeconds: n.avg_duration_seconds,
    };
    return {
      id: n.id,
      type: "activity",
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      data,
    };
  });

  return { nodes, edges: [] };
}

function edgeColor(value: number, max: number, mode: EdgeColorMode): string {
  const t = max > 0 ? value / max : 0;
  if (mode === "frequency") {
    // light blue -> deep blue as frequency rises
    return `hsl(214, ${55 + t * 35}%, ${70 - t * 35}%)`;
  }
  // green (fast) -> red (slow) for time
  return `hsl(${(1 - t) * 130}, 75%, 45%)`;
}

function buildEdges(
  graph: ProcessGraphData,
  mode: EdgeColorMode,
  highlight: Set<string> | null,
  bottleneckEdges: Set<string>,
): Edge[] {
  const maxFreq = Math.max(1, ...graph.edges.map((e) => e.frequency));
  const maxTime = Math.max(1, ...graph.edges.map((e) => e.avg_duration_seconds));
  return graph.edges.map((e) => {
    const id = `${e.source}->${e.target}`;
    const onPath = highlight?.has(id) ?? false;
    const isBottleneck = bottleneckEdges.has(id);
    const dimmed = highlight != null && !onPath;
    const value = mode === "frequency" ? e.frequency : e.avg_duration_seconds;
    const max = mode === "frequency" ? maxFreq : maxTime;
    const color = isBottleneck
      ? "#dc2626"
      : onPath
        ? "#f97316"
        : edgeColor(value, max, mode);
    const baseWidth = 1 + (mode === "frequency" ? e.frequency / maxFreq : 0.5) * 5;
    const width = isBottleneck || onPath ? Math.max(baseWidth, 3.5) : baseWidth;
    return {
      id,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      animated: onPath || isBottleneck || e.frequency / maxFreq > 0.5,
      label:
        mode === "frequency"
          ? e.frequency.toLocaleString()
          : formatDuration(e.avg_duration_seconds),
      labelBgPadding: [4, 2] as [number, number],
      labelStyle: { fontSize: 10, fill: "#334155" },
      labelBgStyle: { fill: "#f8fafc", fillOpacity: 0.9 },
      style: {
        stroke: color,
        strokeWidth: width,
        opacity: dimmed && !isBottleneck ? 0.18 : 1,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color },
    };
  });
}

interface Props {
  logId: string;
  logName: string;
  onClose: () => void;
}

function ProcessGraphInner({ logId, logName, onClose }: Props) {
  const [params, setParams] = useState<DiscoveryParams>({
    dependency_threshold: 0.5,
    frequency_threshold: 1,
  });
  const [algorithm, setAlgorithm] = useState<Algorithm>("heuristic");
  const [colorMode, setColorMode] = useState<EdgeColorMode>("frequency");
  const [graph, setGraph] = useState<ProcessGraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<ActivityCardData | null>(null);
  const [sidePanel, setSidePanel] = useState<SidePanel>(null);
  const [variant, setVariant] = useState<Variant | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottleneckReport | null>(null);
  const [exporting, setExporting] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const runDiscovery = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const data =
        algorithm === "inductive"
          ? await discoverInductiveMiner(logId)
          : await discoverHeuristicMiner(logId, params);
      setGraph(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [logId, params, algorithm]);

  useEffect(() => {
    runDiscovery();
  }, [runDiscovery]);

  const laidOut = useMemo(() => (graph ? layout(graph) : null), [graph]);

  const highlight = useMemo(
    () => (variant ? pathEdgeIds(variant.sequence) : null),
    [variant],
  );

  const bottleneckEdges = useMemo(() => {
    const s = new Set<string>();
    bottlenecks?.bottlenecks.forEach((b) => {
      if (b.kind === "transition" && b.target) s.add(`${b.source}->${b.target}`);
    });
    return s;
  }, [bottlenecks]);

  const bottleneckNodes = useMemo(() => {
    const s = new Set<string>();
    bottlenecks?.bottlenecks.forEach((b) => {
      if (b.kind === "activity") s.add(b.source);
    });
    return s;
  }, [bottlenecks]);

  useEffect(() => {
    if (!laidOut) return;
    setNodes(
      laidOut.nodes.map((n) => ({
        ...n,
        data: {
          ...(n.data as ActivityCardData),
          isBottleneck: bottleneckNodes.has(n.id),
        },
      })),
    );
  }, [laidOut, bottleneckNodes, setNodes]);

  useEffect(() => {
    if (graph) setEdges(buildEdges(graph, colorMode, highlight, bottleneckEdges));
  }, [graph, colorMode, highlight, bottleneckEdges, setEdges]);

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelected(node.data as ActivityCardData);
  }, []);

  async function exportBpmn() {
    setExporting(true);
    setError(null);
    try {
      await downloadBpmn(logId, logName);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setExporting(false);
    }
  }

  function togglePanel(panel: Exclude<SidePanel, null>) {
    setSidePanel((p) => (p === panel ? null : panel));
  }

  return (
    <div className="graph-view">
      <div className="graph-toolbar">
        <div>
          <strong>{logName}</strong>{" "}
          <span className="muted">
            {graph
              ? `${graph.nodes.length} activities · ${graph.edges.length} paths · ${graph.case_count} cases`
              : "discovering…"}
          </span>
        </div>
        <div className="graph-controls">
          <div className="seg" title="Discovery algorithm">
            <button
              className={algorithm === "heuristic" ? "active" : ""}
              onClick={() => setAlgorithm("heuristic")}
            >
              Heuristic
            </button>
            <button
              className={algorithm === "inductive" ? "active" : ""}
              onClick={() => setAlgorithm("inductive")}
            >
              Inductive
            </button>
          </div>
          {algorithm === "heuristic" && (
            <>
              <label>
                Dependency ≥ {params.dependency_threshold.toFixed(2)}
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={params.dependency_threshold}
                  onChange={(e) =>
                    setParams((p) => ({
                      ...p,
                      dependency_threshold: Number(e.target.value),
                    }))
                  }
                />
              </label>
              <label>
                Min frequency {params.frequency_threshold}
                <input
                  type="range"
                  min={1}
                  max={20}
                  step={1}
                  value={params.frequency_threshold}
                  onChange={(e) =>
                    setParams((p) => ({
                      ...p,
                      frequency_threshold: Number(e.target.value),
                    }))
                  }
                />
              </label>
            </>
          )}
          <div className="seg">
            <button
              className={colorMode === "frequency" ? "active" : ""}
              onClick={() => setColorMode("frequency")}
            >
              Frequency
            </button>
            <button
              className={colorMode === "time" ? "active" : ""}
              onClick={() => setColorMode("time")}
            >
              Time
            </button>
          </div>
          <button
            className={sidePanel === "variants" ? "" : "secondary"}
            onClick={() => togglePanel("variants")}
          >
            Variants
          </button>
          <button
            className={sidePanel === "performance" ? "" : "secondary"}
            onClick={() => togglePanel("performance")}
          >
            Performance
          </button>
          <button
            className={sidePanel === "bottlenecks" ? "" : "secondary"}
            onClick={() => togglePanel("bottlenecks")}
          >
            Bottlenecks
          </button>
          <button
            className={sidePanel === "conformance" ? "" : "secondary"}
            onClick={() => togglePanel("conformance")}
          >
            Conformance
          </button>
          <button className="secondary" onClick={exportBpmn} disabled={exporting}>
            {exporting ? "Exporting…" : "Export BPMN"}
          </button>
          <button className="secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {busy && <div className="muted graph-loading">Discovering process…</div>}

      <div className="graph-body">
        <div className="graph-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onPaneClick={() => setSelected(null)}
            fitView
            minZoom={0.1}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>

          {variant && (
            <div className="path-banner">
              Highlighting variant #{variant.rank} ({variant.percentage.toFixed(1)}%)
              <button className="link" onClick={() => setVariant(null)}>
                clear
              </button>
            </div>
          )}

          {selected && (
          <div className="node-detail">
            <h3>{selected.label}</h3>
            <dl>
              <dt>Frequency</dt>
              <dd>{selected.frequency.toLocaleString()} events</dd>
              <dt>Avg time to next</dt>
              <dd>{formatDuration(selected.avgDurationSeconds)}</dd>
              <dt>Role</dt>
              <dd>
                {[
                  selected.isStart ? "start" : null,
                  selected.isEnd ? "end" : null,
                ]
                  .filter(Boolean)
                  .join(", ") || "intermediate"}
              </dd>
            </dl>
            <button className="secondary" onClick={() => setSelected(null)}>
              Dismiss
            </button>
          </div>
        )}
        </div>

        {sidePanel === "variants" && (
          <VariantsPanel
            logId={logId}
            selectedRank={variant?.rank ?? null}
            onSelect={setVariant}
          />
        )}
        {sidePanel === "performance" && <PerformancePanel logId={logId} />}
        {sidePanel === "bottlenecks" && (
          <BottlenecksPanel
            logId={logId}
            logName={logName}
            onChange={setBottlenecks}
          />
        )}
        {sidePanel === "conformance" && (
          <ConformancePanel
            logId={logId}
            onChange={() => {}}
          />
        )}
      </div>
    </div>
  );
}

export default function ProcessGraph(props: Props) {
  return (
    <ReactFlowProvider>
      <ProcessGraphInner {...props} />
    </ReactFlowProvider>
  );
}
