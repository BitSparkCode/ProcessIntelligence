import { useCallback, useEffect, useState } from "react";
import {
  getCaseEvents,
  listCases,
  type CaseDetailReport,
  type CaseListReport,
  type LogFilter,
} from "../api";
import { formatDuration } from "../format";

interface Props {
  logId: string;
  filters?: LogFilter;
  onShowPath: (sequence: string[] | null, caseKey: string | null) => void;
}

const PAGE_SIZE = 20;

export default function CasesPanel({ logId, filters, onShowPath }: Props) {
  const [report, setReport] = useState<CaseListReport | null>(null);
  const [detail, setDetail] = useState<CaseDetailReport | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("duration");
  const [desc, setDesc] = useState(true);
  const [shownPath, setShownPath] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listCases(logId, {
      page,
      page_size: PAGE_SIZE,
      sort,
      descending: desc,
      search,
      filters,
    })
      .then((r) => active && setReport(r))
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [logId, page, sort, desc, search, filters]);

  const openCase = useCallback(
    (caseKey: string) => {
      getCaseEvents(logId, caseKey)
        .then(setDetail)
        .catch((e) => setDetailError((e as Error).message));
    },
    [logId],
  );

  function togglePath() {
    if (!detail) return;
    if (shownPath === detail.case_key) {
      setShownPath(null);
      onShowPath(null, null);
    } else {
      setShownPath(detail.case_key);
      onShowPath(detail.events.map((e) => e.activity), detail.case_key);
    }
  }

  const pages = report ? Math.max(1, Math.ceil(report.total_cases / PAGE_SIZE)) : 1;

  if (detail) {
    return (
      <div className="side-panel">
        <div className="side-panel__head">
          <h3>Case {detail.case_key}</h3>
          <button
            className="link"
            onClick={() => {
              setDetail(null);
              setDetailError(null);
              setShownPath(null);
              onShowPath(null, null);
            }}
          >
            ← back
          </button>
        </div>
        {detailError && <div className="error">{detailError}</div>}
        <div className="kpi-grid">
          <div className="kpi">
            <span className="kpi__label">Duration</span>
            <span className="kpi__value">{formatDuration(detail.duration_seconds)}</span>
          </div>
          <div className="kpi">
            <span className="kpi__label">Events</span>
            <span className="kpi__value">{detail.event_count}</span>
          </div>
        </div>
        <p className="muted side-note">
          {detail.start.slice(0, 19).replace("T", " ")} →{" "}
          {detail.end.slice(0, 19).replace("T", " ")}
        </p>
        <button onClick={togglePath}>
          {shownPath === detail.case_key ? "Hide path on map" : "Show path on map"}
        </button>
        <table className="perf-table" style={{ marginTop: 10 }}>
          <thead>
            <tr>
              <th>Activity</th>
              <th>Time</th>
              <th>Wait</th>
            </tr>
          </thead>
          <tbody>
            {detail.events.map((e, i) => (
              <tr key={i}>
                <td>
                  {e.activity}
                  {e.resource && <div className="muted">{e.resource}</div>}
                </td>
                <td className="muted">{e.timestamp.slice(5, 19).replace("T", " ")}</td>
                <td>{formatDuration(e.gap_to_next_seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="side-panel">
      <div className="side-panel__head">
        <h3>Cases</h3>
        {report && <span className="muted">{report.total_cases} total</span>}
      </div>

      <input
        type="text"
        placeholder="Search case key…"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
        style={{ width: "100%" }}
      />

      <div className="seg seg--sm" style={{ marginTop: 8 }}>
        {(["duration", "events", "start"] as const).map((s) => (
          <button
            key={s}
            className={sort === s ? "active" : ""}
            onClick={() => {
              setSort(s);
              setPage(1);
            }}
          >
            {s}
          </button>
        ))}
        <button onClick={() => setDesc((d) => !d)}>{desc ? "↓" : "↑"}</button>
      </div>

      {error && <div className="error">{error}</div>}

      <table className="perf-table" style={{ marginTop: 10 }}>
        <thead>
          <tr>
            <th>Case</th>
            <th>Events</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          {report?.cases.map((c) => (
            <tr key={c.case_key}>
              <td>
                <button className="link" onClick={() => openCase(c.case_key)}>
                  {c.case_key}
                </button>
                <div className="muted case-variant">
                  {c.variant.slice(0, 4).join(" → ")}
                  {c.variant.length > 4 && " …"}
                </div>
              </td>
              <td>{c.event_count}</td>
              <td>{formatDuration(c.duration_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="pager">
        <button
          className="secondary"
          disabled={page <= 1}
          onClick={() => setPage((p) => p - 1)}
        >
          ‹
        </button>
        <span className="muted">
          {page} / {pages}
        </span>
        <button
          className="secondary"
          disabled={page >= pages}
          onClick={() => setPage((p) => p + 1)}
        >
          ›
        </button>
      </div>
    </div>
  );
}
