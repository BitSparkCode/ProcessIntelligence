import { useEffect, useState } from "react";
import { analyzePerformance, type PerformanceReport } from "../api";
import { formatDuration } from "../format";

interface Props {
  logId: string;
}

const WINDOWS: { label: string; value: number | null }[] = [
  { label: "All", value: null },
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
  { label: "365d", value: 365 },
];

export default function PerformancePanel({ logId }: Props) {
  const [report, setReport] = useState<PerformanceReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [windowDays, setWindowDays] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    analyzePerformance(logId, { window_days: windowDays, histogram_bins: 12 })
      .then((r) => active && setReport(r))
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [logId, windowDays]);

  const maxBin = report
    ? Math.max(1, ...report.histogram.map((b) => b.count))
    : 1;

  return (
    <div className="side-panel">
      <div className="side-panel__head">
        <h3>Throughput</h3>
        {report && <span className="muted">{report.case_count} cases</span>}
      </div>

      <div className="seg seg--sm">
        {WINDOWS.map((w) => (
          <button
            key={w.label}
            className={windowDays === w.value ? "active" : ""}
            onClick={() => setWindowDays(w.value)}
          >
            {w.label}
          </button>
        ))}
      </div>

      {error && <div className="error">{error}</div>}

      {report && (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <span className="kpi__label">Average</span>
              <span className="kpi__value">
                {formatDuration(report.avg_throughput_seconds)}
              </span>
            </div>
            <div className="kpi">
              <span className="kpi__label">Median</span>
              <span className="kpi__value">
                {formatDuration(report.median_throughput_seconds)}
              </span>
            </div>
            <div className="kpi">
              <span className="kpi__label">Min</span>
              <span className="kpi__value">
                {formatDuration(report.min_throughput_seconds)}
              </span>
            </div>
            <div className="kpi">
              <span className="kpi__label">Max</span>
              <span className="kpi__value">
                {formatDuration(report.max_throughput_seconds)}
              </span>
            </div>
          </div>

          <h4 className="side-h4">Throughput distribution</h4>
          <div className="histogram">
            {report.histogram.map((b, i) => (
              <div
                key={i}
                className="histogram__bar"
                title={`${formatDuration(b.lower_seconds)}–${formatDuration(
                  b.upper_seconds,
                )}: ${b.count} cases`}
              >
                <span style={{ height: `${(b.count / maxBin) * 100}%` }} />
              </div>
            ))}
          </div>

          <h4 className="side-h4">Slowest transitions (waiting time)</h4>
          <table className="perf-table">
            <thead>
              <tr>
                <th>Transition</th>
                <th>Avg wait</th>
                <th>n</th>
              </tr>
            </thead>
            <tbody>
              {[...report.transition_stats]
                .sort((a, b) => b.avg_waiting_seconds - a.avg_waiting_seconds)
                .slice(0, 8)
                .map((t) => (
                  <tr key={`${t.source}->${t.target}`}>
                    <td>
                      {t.source} → {t.target}
                    </td>
                    <td>{formatDuration(t.avg_waiting_seconds)}</td>
                    <td>{t.frequency}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
