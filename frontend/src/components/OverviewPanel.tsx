import { useEffect, useState } from "react";
import { getOverview, type LogFilter, type OverviewReport } from "../api";
import { formatDuration } from "../format";

interface Props {
  logId: string;
  filters?: LogFilter;
}

export default function OverviewPanel({ logId, filters }: Props) {
  const [report, setReport] = useState<OverviewReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getOverview(logId, 30, filters)
      .then((r) => active && setReport(r))
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [logId, filters]);

  if (error) return <div className="side-panel"><div className="error">{error}</div></div>;
  if (!report) return <div className="side-panel"><p className="muted">Loading…</p></div>;

  const maxBucket = Math.max(1, ...report.cases_over_time.map((b) => b.count));
  const maxAct = Math.max(1, ...report.top_activities.map((a) => a.count));
  const maxRes = Math.max(1, ...report.top_resources.map((r) => r.count));

  return (
    <div className="side-panel">
      <div className="side-panel__head">
        <h3>Overview</h3>
        <span className="muted">log statistics</span>
      </div>

      <div className="kpi-grid">
        <div className="kpi">
          <span className="kpi__label">Cases</span>
          <span className="kpi__value">{report.case_count.toLocaleString()}</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">Events</span>
          <span className="kpi__value">{report.event_count.toLocaleString()}</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">Activities</span>
          <span className="kpi__value">{report.activity_count}</span>
        </div>
        <div className="kpi">
          <span className="kpi__label">Median throughput</span>
          <span className="kpi__value">
            {formatDuration(report.median_throughput_seconds)}
          </span>
        </div>
      </div>

      {report.first_event && report.last_event && (
        <p className="muted side-note">
          {report.first_event.slice(0, 10)} → {report.last_event.slice(0, 10)} ·
          mean {formatDuration(report.mean_throughput_seconds)}
        </p>
      )}

      <h4 className="side-h4">Cases over time</h4>
      <div className="timeseries">
        {report.cases_over_time.map((b, i) => (
          <div
            key={i}
            className="timeseries__bar"
            title={`${b.start.slice(0, 10)}: ${b.count} cases`}
          >
            <span style={{ height: `${(b.count / maxBucket) * 100}%` }} />
          </div>
        ))}
      </div>

      <h4 className="side-h4">Top activities</h4>
      <ul className="toplist">
        {report.top_activities.map((a) => (
          <li key={a.name}>
            <span className="toplist__name">{a.name}</span>
            <span className="toplist__bar">
              <span style={{ width: `${(a.count / maxAct) * 100}%` }} />
            </span>
            <span className="toplist__count">{a.count.toLocaleString()}</span>
          </li>
        ))}
      </ul>

      {report.top_resources.length > 0 && (
        <>
          <h4 className="side-h4">Top resources</h4>
          <ul className="toplist">
            {report.top_resources.map((r) => (
              <li key={r.name}>
                <span className="toplist__name">{r.name}</span>
                <span className="toplist__bar">
                  <span style={{ width: `${(r.count / maxRes) * 100}%` }} />
                </span>
                <span className="toplist__count">{r.count.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
