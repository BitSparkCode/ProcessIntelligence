import { useCallback, useRef, useState } from "react";
import { type ConformanceReport, checkConformance } from "../api";

interface Props {
  logId: string;
  onChange: (report: ConformanceReport | null) => void;
}

export default function ConformancePanel({ logId, onChange }: Props) {
  const [report, setReport] = useState<ConformanceReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [method, setMethod] = useState<"alignment" | "token">("alignment");
  const [explain, setExplain] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = useCallback(
    async (file: File) => {
      setBusy(true);
      setError(null);
      try {
        const r = await checkConformance(logId, file, { method, explain });
        setReport(r);
        onChange(r);
      } catch (e) {
        setError((e as Error).message);
        onChange(null);
      } finally {
        setBusy(false);
      }
    },
    [logId, method, explain, onChange],
  );

  function handleFile(f: File) {
    run(f);
  }

  return (
    <div className="side-panel">
      <div className="side-panel__head">
        <h3>Conformance</h3>
        {report && (
          <span className="muted">
            fitness {(report.fitness * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <label className="side-field">
        Reference model (.bpmn)
        <input
          ref={fileRef}
          type="file"
          accept=".bpmn,.xml"
          onChange={(e) =>
            e.target.files?.[0] && handleFile(e.target.files[0])
          }
          disabled={busy}
          style={{ marginTop: 4, fontSize: "0.85rem" }}
        />
      </label>

      <label className="side-field">
        Method
        <div className="seg seg--sm">
          <button
            className={method === "alignment" ? "active" : ""}
            onClick={() => setMethod("alignment")}
          >
            Alignment
          </button>
          <button
            className={method === "token" ? "active" : ""}
            onClick={() => setMethod("token")}
          >
            Token replay
          </button>
        </div>
      </label>

      <label className="side-field" style={{ cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={explain}
          onChange={(e) => setExplain(e.target.checked)}
          style={{ marginRight: 6 }}
        />
        AI explanation
      </label>

      {busy && <p className="muted">Checking conformance…</p>}
      {error && <div className="error">{error}</div>}

      {report && !busy && (
        <>
          {/* KPIs */}
          <div className="conf-kpis">
            <div className="conf-kpi">
              <span className="conf-kpi__value">
                {(report.fitness * 100).toFixed(1)}%
              </span>
              <span className="conf-kpi__label">Fitness</span>
            </div>
            <div className="conf-kpi">
              <span className="conf-kpi__value">
                {report.fitting_case_count}/{report.case_count}
              </span>
              <span className="conf-kpi__label">Conforming</span>
            </div>
            <div className="conf-kpi">
              <span className="conf-kpi__value">
                {report.percentage_fitting.toFixed(0)}%
              </span>
              <span className="conf-kpi__label">Pct. fitting</span>
            </div>
          </div>

          {/* AI / heuristic explanation */}
          {report.explanation && (
            <div className="conf-explanation">
              <strong>
                {report.explanation_source === "ai" ? "AI" : "Summary"}:
              </strong>{" "}
              {report.explanation}
            </div>
          )}

          {/* Deviation summary */}
          {report.deviation_summary.length > 0 && (
            <>
              <h4 className="side-h4">Deviations by frequency</h4>
              <ol className="bottleneck-list">
                {report.deviation_summary.map((d) => (
                  <li
                    key={`${d.kind}:${d.activity}`}
                    className="bottleneck-row"
                  >
                    <div className="bottleneck-row__head">
                      <span
                        className={`conf-kind conf-kind--${d.kind}`}
                      >
                        {d.kind}
                      </span>
                      <span className="bottleneck-row__label">
                        {d.activity}
                      </span>
                      <span className="bottleneck-row__sev">
                        {d.case_count}×
                      </span>
                    </div>
                    <div className="bottleneck-row__meta muted">
                      {d.description}
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}

          {/* Per-case details (collapsed by default) */}
          <CaseDetails cases={report.case_deviations} />
        </>
      )}
    </div>
  );
}

function CaseDetails(props: {
  cases: ConformanceReport["case_deviations"];
}) {
  const [open, setOpen] = useState(false);
  const bad = props.cases.filter((c) => !c.is_fitting);
  if (bad.length === 0) return null;
  return (
    <>
      <button
        className="secondary side-export"
        onClick={() => setOpen(!open)}
        style={{ marginTop: 8 }}
      >
        {open ? "Hide" : "Show"} non-conforming cases ({bad.length})
      </button>
      {open && (
        <ul className="conf-cases">
          {bad.map((c) => (
            <li key={c.case_key} className="conf-case">
              <strong>{c.case_key}</strong>{" "}
              <span className="muted">
                fitness {(c.fitness * 100).toFixed(0)}%
              </span>
              <ul>
                {c.deviations.map((d, i) => (
                  <li key={i} className="muted">
                    {d}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
