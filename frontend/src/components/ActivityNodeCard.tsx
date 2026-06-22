import { Handle, Position, type NodeProps } from "@xyflow/react";
import { formatDuration } from "../format";

export interface ActivityCardData {
  label: string;
  frequency: number;
  maxFrequency: number;
  isStart: boolean;
  isEnd: boolean;
  avgDurationSeconds: number | null;
  isBottleneck?: boolean;
  [key: string]: unknown;
}

export default function ActivityNodeCard({ data, selected }: NodeProps) {
  const d = data as ActivityCardData;
  const intensity = d.maxFrequency > 0 ? d.frequency / d.maxFrequency : 0;
  // Frequency drives the accent strength: hotter activities glow brighter.
  const accent = `hsl(${214 - intensity * 40}, ${60 + intensity * 30}%, ${
    62 - intensity * 18
  }%)`;
  const borderColor = d.isBottleneck ? "#dc2626" : accent;

  return (
    <div
      className={`activity-node${selected ? " selected" : ""}${
        d.isBottleneck ? " bottleneck" : ""
      }`}
      style={{ borderColor }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="activity-node__bar" style={{ background: accent }} />
      <div className="activity-node__body">
        <div className="activity-node__title">{d.label}</div>
        <div className="activity-node__kpis">
          <span title="Event frequency">▦ {d.frequency.toLocaleString()}</span>
          <span title="Avg time to next activity">⏱ {formatDuration(d.avgDurationSeconds)}</span>
        </div>
        <div className="activity-node__tags">
          {d.isStart && <span className="tag tag--start">start</span>}
          {d.isEnd && <span className="tag tag--end">end</span>}
          {d.isBottleneck && <span className="tag tag--bottleneck">bottleneck</span>}
        </div>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
