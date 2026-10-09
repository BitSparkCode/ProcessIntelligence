import { useEffect, useMemo, useRef, useState } from "react";
import { useViewport, type Node } from "@xyflow/react";
import { getReplay, type LogFilter, type ReplayReport } from "../api";
import { formatDuration } from "../format";

interface Props {
  logId: string;
  filters?: LogFilter;
  nodes: Node[];
  onClose: () => void;
}

const SPEEDS = [0.5, 1, 2, 4];
const PLAY_SECONDS = 30; // wall-clock duration of a full replay

function findActivity(events: [string, number][], t: number): string | null {
  let lo = 0;
  let hi = events.length - 1;
  let result: string | null = null;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (events[mid][1] <= t) {
      result = events[mid][0];
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return result;
}

export default function ReplayOverlay({ logId, filters, nodes, onClose }: Props) {
  const [replay, setReplay] = useState<ReplayReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(1);
  const raf = useRef<number>(0);
  const { x, y, zoom } = useViewport();

  useEffect(() => {
    let active = true;
    getReplay(logId, filters)
      .then((r) => {
        if (!active) return;
        setReplay(r);
        if (r.cases.length > 0 && r.horizon_seconds > 0) setPlaying(true);
      })
      .catch((e) => active && setError((e as Error).message));
    return () => {
      active = false;
    };
  }, [logId, filters]);

  useEffect(() => {
    if (!playing || !replay) return;
    let last = performance.now();
    const horizon = replay.horizon_seconds || 1;
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setT((prev) => {
        const next = prev + (horizon / PLAY_SECONDS) * SPEEDS[speedIdx] * dt;
        if (next >= horizon) {
          setPlaying(false);
          return horizon;
        }
        return next;
      });
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [playing, replay, speedIdx]);

  const centers = useMemo(() => {
    const m = new Map<string, { cx: number; cy: number }>();
    for (const n of nodes) {
      m.set(n.id, {
        cx: (n.position.x + 100) * zoom + x,
        cy: (n.position.y + 48) * zoom + y,
      });
    }
    return m;
  }, [nodes, x, y, zoom]);

  const tokens = useMemo(() => {
    if (!replay) return [];
    const perActivity = new Map<string, number>();
    const out: { x: number; y: number; key: string }[] = [];
    for (const c of replay.cases) {
      const act = findActivity(c.events, t);
      if (!act) continue;
      const center = centers.get(act);
      if (!center) continue;
      const idx = (perActivity.get(act) ?? 0) + 1;
      perActivity.set(act, idx);
      // golden-angle spiral spread so stacked cases stay visible
      const angle = idx * 2.39996;
      const radius = Math.min(3 + Math.sqrt(idx) * 7, 34) * Math.max(zoom, 0.5);
      out.push({
        key: c.case_key,
        x: center.cx + Math.cos(angle) * radius,
        y: center.cy + Math.sin(angle) * radius,
      });
    }
    return out;
  }, [replay, t, centers, zoom]);

  const horizon = replay?.horizon_seconds ?? 0;

  return (
    <>
      <div className="replay-layer">
        {tokens.map((tk) => (
          <span
            key={tk.key}
            className="replay-token"
            style={{ transform: `translate(${tk.x}px, ${tk.y}px)` }}
          />
        ))}
      </div>
      <div className="replay-bar">
        <button
          className="replay-bar__play"
          onClick={() => {
            if (t >= horizon) setT(0);
            setPlaying((p) => !p);
          }}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          min={0}
          max={horizon}
          step={horizon / 500 || 1}
          value={t}
          onChange={(e) => {
            setPlaying(false);
            setT(Number(e.target.value));
          }}
        />
        <span className="replay-bar__time">
          {formatDuration(t)} / {formatDuration(horizon)}
        </span>
        <div className="seg seg--sm">
          {SPEEDS.map((s, i) => (
            <button
              key={s}
              className={speedIdx === i ? "active" : ""}
              onClick={() => setSpeedIdx(i)}
            >
              {s}×
            </button>
          ))}
        </div>
        <button className="secondary" onClick={onClose}>
          Stop
        </button>
      </div>
      {error && <div className="error replay-error">{error}</div>}
      {replay && !error && (
        <div className="replay-count">{replay.case_count} cases replaying</div>
      )}
    </>
  );
}
