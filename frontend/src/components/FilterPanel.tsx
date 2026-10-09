import { useId, useMemo, useState } from "react";
import type { LogFilter } from "../api";

interface Props {
  logId: string;
  activities: string[];
  resources: string[];
  value: LogFilter;
  onApply: (filters: LogFilter) => void;
}

export function activeFilterCount(f: LogFilter): number {
  let n = 0;
  if (f.from_ts || f.to_ts) n++;
  if (f.start_activities?.length) n++;
  if (f.end_activities?.length) n++;
  if (f.include_activities?.length) n++;
  if (f.exclude_activities?.length) n++;
  if (f.resources?.length) n++;
  if (f.min_duration_seconds || f.max_duration_seconds) n++;
  return n;
}

function TagInput(props: {
  label: string;
  hint?: string;
  values: string[];
  suggestions: string[];
  onChange: (v: string[]) => void;
}) {
  const dlId = useId();
  const [text, setText] = useState("");

  function add(raw: string) {
    const v = raw.trim();
    if (v && !props.values.includes(v)) props.onChange([...props.values, v]);
    setText("");
  }

  return (
    <div className="filter-field">
      <span className="filter-label">
        {props.label}
        {props.values.length > 0 && ` (${props.values.length})`}
      </span>
      <div className="tag-chips">
        {props.values.map((v) => (
          <span key={v} className="chip">
            {v}
            <button
              type="button"
              className="chip__x"
              onClick={() => props.onChange(props.values.filter((x) => x !== v))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          list={dlId}
          value={text}
          placeholder={props.hint ?? "type or pick…"}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add(text);
            }
          }}
          onBlur={() => text && add(text)}
        />
        <datalist id={dlId}>
          {props.suggestions
            .filter((s) => !props.values.includes(s))
            .map((s) => (
              <option key={s} value={s} />
            ))}
        </datalist>
      </div>
    </div>
  );
}

export default function FilterPanel({
  activities,
  resources,
  value,
  onApply,
}: Props) {
  const [draft, setDraft] = useState<LogFilter>(value);
  const [minDays, setMinDays] = useState(
    value.min_duration_seconds ? value.min_duration_seconds / 86400 : "",
  );
  const [maxDays, setMaxDays] = useState(
    value.max_duration_seconds ? value.max_duration_seconds / 86400 : "",
  );
  const active = useMemo(() => activeFilterCount(draft), [draft]);

  function set<K extends keyof LogFilter>(key: K, v: LogFilter[K]) {
    setDraft((d) => ({ ...d, [key]: v }));
  }

  function apply() {
    onApply({
      ...draft,
      min_duration_seconds:
        minDays === "" ? null : Number(minDays) * 86400,
      max_duration_seconds:
        maxDays === "" ? null : Number(maxDays) * 86400,
    });
  }

  function reset() {
    const empty: LogFilter = {};
    setDraft(empty);
    setMinDays("");
    setMaxDays("");
    onApply(empty);
  }

  return (
    <div className="side-panel">
      <div className="side-panel__head">
        <h3>Filters</h3>
        <span className="muted">{active} active</span>
      </div>

      <div className="filter-group">
        <h4 className="side-h4">Timeframe</h4>
        <div className="filter-dates">
          <input
            type="date"
            value={draft.from_ts?.slice(0, 10) ?? ""}
            onChange={(e) =>
              set("from_ts", e.target.value ? `${e.target.value}T00:00:00Z` : null)
            }
          />
          <span className="muted">→</span>
          <input
            type="date"
            value={draft.to_ts?.slice(0, 10) ?? ""}
            onChange={(e) =>
              set("to_ts", e.target.value ? `${e.target.value}T23:59:59Z` : null)
            }
          />
        </div>
      </div>

      <TagInput
        label="Starts with activity"
        values={draft.start_activities ?? []}
        suggestions={activities}
        onChange={(v) => set("start_activities", v)}
      />
      <TagInput
        label="Ends with activity"
        values={draft.end_activities ?? []}
        suggestions={activities}
        onChange={(v) => set("end_activities", v)}
      />
      <TagInput
        label="Include activities"
        hint="keep only these"
        values={draft.include_activities ?? []}
        suggestions={activities}
        onChange={(v) => set("include_activities", v)}
      />
      <TagInput
        label="Exclude activities"
        hint="drop these"
        values={draft.exclude_activities ?? []}
        suggestions={activities}
        onChange={(v) => set("exclude_activities", v)}
      />
      <TagInput
        label="Resources"
        hint="only these resources"
        values={draft.resources ?? []}
        suggestions={resources}
        onChange={(v) => set("resources", v)}
      />

      <div className="filter-group">
        <h4 className="side-h4">Case duration (days)</h4>
        <div className="filter-dates">
          <input
            type="number"
            min={0}
            step={0.5}
            placeholder="min"
            value={minDays}
            onChange={(e) => setMinDays(e.target.value)}
          />
          <span className="muted">→</span>
          <input
            type="number"
            min={0}
            step={0.5}
            placeholder="max"
            value={maxDays}
            onChange={(e) => setMaxDays(e.target.value)}
          />
        </div>
      </div>

      <div className="filter-actions">
        <button onClick={apply}>Apply filters</button>
        <button className="secondary" onClick={reset}>
          Reset
        </button>
      </div>
      <p className="muted side-note">
        Filters apply to the process map, variants, performance, bottlenecks,
        overview and simulation.
      </p>
    </div>
  );
}
