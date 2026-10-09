import { useMemo, useState } from "react";
import {
  runSimulation,
  type LogFilter,
  type SimulationReport,
} from "../api";
import { formatDuration } from "../format";

interface Props {
  logId: string;
  filters?: LogFilter;
  activities: string[];
}

interface Override {
  activity: string;
  servers: string;
  speed: string;
}

export default function SimulationPanel({ logId, filters, activities }: Props) {
  const [cases, setCases] = useState(1000);
  const [arrivalMult, setArrivalMult] = useState(1);
  const [durationMult, setDurationMult] = useState(1);
  const [defaultServers, setDefaultServers] = useState<string>("");
  const [overrides, setOverrides] = useState<Override[]>([]);
  const [report, setReport] = useState<SimulationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const maxBin = report
    ? Math.max(1, ...report.histogram.map((b) => b.count))
    : 1;

  const unusedActivities = useMemo(
    () => activities.filter((a) => !overrides.some((o) => o.activity === a)),
    [activities, overrides],
  );

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const pools: Record<string, number> = {};
      const speeds: Record<string, number> = {};
      for (const o of overrides) {
        if (o.servers !== "") pools[o.activity] = Number(o.servers);
        if (o.speed !== "" && Number(o.speed) !== 1)
          speeds[o.activity] = Number(o.speed);
      }
      const r = await runSimulation(logId, {
        cases,
        arrival_rate_multiplier: arrivalMult,
        global_duration_multiplier: durationMult,
        default_servers: defaultServers === "" ? null : Number(defaultServers),
        resource_pools: pools,
        duration_multipliers: speeds,
        histogram_bins: 12,
        filters,
      });
      setReport(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="side-panel side-panel--wide">
      <div className="side-panel__head">
        <h3>Simulation</h3>
        <span className="muted">what-if scenarios</span>
      </div>

      <div className="side-filters">
        <label>
          Cases {cases.toLocaleString()}
          <input
            type="range"
            min={100}
            max={5000}
            step={100}
            value={cases}
            onChange={(e) => setCases(Number(e.target.value))}
          />
        </label>
        <label>
          Arrival rate ×{arrivalMult.toFixed(2)}
          <input
            type="range"
            min={0.25}
            max={4}
            step={0.25}
            value={arrivalMult}
            onChange={(e) => setArrivalMult(Number(e.target.value))}
          />
        </label>
        <label>
          Activity speed ×{durationMult.toFixed(2)}
          <input
            type="range"
            min={0.25}
            max={4}
            step={0.25}
            value={durationMult}
            onChange={(e) => setDurationMult(Number(e.target.value))}
          />
        </label>
      </div>

      <label className="side-field">
        Capacity per activity (empty = unlimited)
        <input
          type="number"
          min={1}
          placeholder="unlimited"
          value={defaultServers}
          onChange={(e) => setDefaultServers(e.target.value)}
        />
      </label>

      <h4 className="side-h4">Activity overrides</h4>
      {overrides.map((o, i) => (
        <div key={o.activity} className="sim-override">
          <strong>{o.activity}</strong>
          <input
            type="number"
            min={1}
            placeholder="servers"
            value={o.servers}
            onChange={(e) =>
              setOverrides((os) =>
                os.map((x, j) => (j === i ? { ...x, servers: e.target.value } : x)),
              )
            }
          />
          <input
            type="number"
            min={0.1}
            step={0.1}
            placeholder="speed ×"
            value={o.speed}
            onChange={(e) =>
              setOverrides((os) =>
                os.map((x, j) => (j === i ? { ...x, speed: e.target.value } : x)),
              )
            }
          />
          <button
            className="chip__x"
            onClick={() => setOverrides((os) => os.filter((_, j) => j !== i))}
          >
            ×
          </button>
        </div>
      ))}
      {unusedActivities.length > 0 && (
        <select
          value=""
          onChange={(e) =>
            e.target.value &&
            setOverrides((os) => [
              ...os,
              { activity: e.target.value, servers: "", speed: "" },
            ])
          }
        >
          <option value="">+ add activity override…</option>
          {unusedActivities.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      )}

      <p>
        <button onClick={run} disabled={busy}>
          {busy ? "Simulating…" : "Run simulation"}
        </button>
      </p>
      {error && <div className="error">{error}</div>}

      {report && (
        <>
          <div className="kpi-grid">
            <div className="kpi">
              <span className="kpi__label">Mean throughput</span>
              <span className="kpi__value">
                {formatDuration(report.simulated.mean_seconds)}
              </span>
              {report.baseline && (
                <span className="kpi__delta">
                  was {formatDuration(report.baseline.mean_seconds)}
                </span>
              )}
            </div>
            <div className="kpi">
              <span className="kpi__label">P90 throughput</span>
              <span className="kpi__value">
                {formatDuration(report.simulated.p90_seconds)}
              </span>
              {report.baseline && (
                <span className="kpi__delta">
                  was {formatDuration(report.baseline.p90_seconds)}
                </span>
              )}
            </div>
          </div>
          <p className="muted side-note">
            {report.simulated_cases} simulated cases ·{" "}
            {report.arrival_rate_per_day.toFixed(2)} arrivals/day
          </p>

          <h4 className="side-h4">Simulated duration distribution</h4>
          <div className="histogram">
            {report.histogram.map((b, i) => (
              <div
                key={i}
                className="histogram__bar"
                title={`${formatDuration(b.lower_seconds)}–${formatDuration(
                  b.upper_seconds,
                )}: ${b.count}`}
              >
                <span style={{ height: `${(b.count / maxBin) * 100}%` }} />
              </div>
            ))}
          </div>

          <h4 className="side-h4">Per activity</h4>
          <table className="perf-table">
            <thead>
              <tr>
                <th>Activity</th>
                <th>Execs</th>
                <th>Servers</th>
                <th>Avg wait</th>
                <th>Util.</th>
              </tr>
            </thead>
            <tbody>
              {report.activity_stats.map((s) => (
                <tr key={s.activity}>
                  <td>{s.activity}</td>
                  <td>{s.executions.toLocaleString()}</td>
                  <td>{s.servers ?? "∞"}</td>
                  <td>{formatDuration(s.mean_wait_seconds)}</td>
                  <td>
                    {s.utilization != null
                      ? `${Math.round(s.utilization * 100)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
