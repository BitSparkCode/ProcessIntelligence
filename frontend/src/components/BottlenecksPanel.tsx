import { useEffect, useState } from "react";
import {
  type BottleneckReport,
  detectBottlenecks,
  downloadBottlenecks,
} from "../api";
import { formatDuration } from "../format";

interface Props {
  logId: string;
  logName: string;
  onChange: (report: BottleneckReport | null) => void;
}

const PERCENTILES = [75, 90, 95];

export default function BottlenecksPanel({ logId, logName, onChange }: Props) {
  const [report, setReport] = useState<BottleneckReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [percentile, setPercentile] = useState(90);

  useEffect(() => {
    let active = true;
    detectBottlenecks(logId, { percentile, top_n: 5 })
      .then((r) => {
        if (active) {
          setReport(r);
          onChange(r);
        }
      })
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [logId, percentile, onChange]);

  // Clear the graph highlight when the panel unmounts.
  useEffect(() => () => onChange(null), [onChange]);

  return (
    <div className="side-panel">
      <div className="side-panel__head">
        <h3>Bottlenecks</h3>
        {report && (
          <span className="muted">{report.bottleneck_count} flagged</span>
        )}
      </div>

      <label className="side-field">
        Percentile threshold
        <div className="seg seg--sm">
          {PERCENTILES.map((p) => (
            <button
              key={p}
              className={percentile === p ? "active" : ""}
              onClick={() => setPercentile(p)}
            >
              {p}th
            </button>
          ))}
        </div>
      </label>

      {error && <div className="error">{error}</div>}

      {report && (
        <>
          <p className="muted side-note">
            Flagging steps whose mean waiting time exceeds the {report.percentile}
            th percentile ({formatDuration(report.threshold_seconds)}).
          </p>

          <h4 className="side-h4">Top {report.top.length} bottlenecks</h4>
          {report.top.length === 0 ? (
            <p className="muted">None detected at this threshold.</p>
          ) : (
            <ol className="bottleneck-list">
              {report.top.map((b, i) => (
                <li key={`${b.kind}:${b.label}`} className="bottleneck-row">
                  <div className="bottleneck-row__head">
                    <span className="bottleneck-row__rank">{i + 1}</span>
                    <span className="bottleneck-row__label">{b.label}</span>
                    <span className="bottleneck-row__sev">
                      {b.severity.toFixed(1)}×
                    </span>
                  </div>
                  <div className="bottleneck-row__meta muted">
                    {b.kind} · avg {formatDuration(b.avg_waiting_seconds)} · max{" "}
                    {formatDuration(b.max_waiting_seconds)} · {b.frequency}×
                  </div>
                </li>
              ))}
            </ol>
          )}

          <button
            className="secondary side-export"
            onClick={() => downloadBottlenecks(logId, logName, percentile)}
          >
            Export summary (.txt)
          </button>
        </>
      )}
    </div>
  );
}
