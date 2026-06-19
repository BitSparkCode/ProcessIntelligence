import { useState } from "react";
import {
  ColumnMapping,
  CsvPreview,
  importCsv,
  MappingSuggestion,
  uploadCsv,
} from "../api";

interface Props {
  onImported: () => void;
}

const OPTIONAL_FIELDS: { key: keyof ColumnMapping; label: string }[] = [
  { key: "resource", label: "Resource (optional)" },
  { key: "cost", label: "Activity cost (optional)" },
  { key: "lifecycle", label: "Lifecycle status (optional)" },
];

export default function CsvImport({ onImported }: Props) {
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [name, setName] = useState("");
  const [mapping, setMapping] = useState<ColumnMapping>({
    case_id: "",
    activity: "",
    timestamp: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [suggestion, setSuggestion] = useState<MappingSuggestion | null>(null);

  async function handleFile(file: File) {
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      const resp = await uploadCsv(file);
      setUploadId(resp.upload_id);
      setPreview(resp.preview);
      setName(file.name.replace(/\.csv$/i, ""));
      setSuggestion(resp.suggestion);
      // Prefill from the server's AI/heuristic data-linking suggestion (Story 6.1).
      const m = resp.suggestion.mapping;
      setMapping({
        case_id: m.case_id ?? "",
        activity: m.activity ?? "",
        timestamp: m.timestamp ?? "",
        resource: m.resource ?? null,
        cost: m.cost ?? null,
        lifecycle: m.lifecycle ?? null,
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleImport() {
    if (!uploadId) return;
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      const result = await importCsv(uploadId, name || "Untitled log", mapping);
      setSuccess(
        `Imported "${result.name}": ${result.row_count} events, ` +
          `${result.case_count} cases, ${result.activity_count} activities.`,
      );
      setUploadId(null);
      setPreview(null);
      setSuggestion(null);
      onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const canImport =
    !!uploadId && !!mapping.case_id && !!mapping.activity && !!mapping.timestamp && !busy;

  return (
    <div>
      <input
        type="file"
        accept=".csv"
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        disabled={busy}
      />
      {error && <div className="error">{error}</div>}
      {success && <div className="success">{success}</div>}

      {preview && (
        <>
          <h3>Map columns</h3>
          {suggestion && (
            <div className={`suggestion-banner suggestion-banner--${suggestion.source}`}>
              <strong>
                {suggestion.ai_enabled ? "AI suggested" : "Auto-detected"} a mapping
              </strong>{" "}
              <span className="muted">
                ({suggestion.source}, confidence {Math.round(suggestion.confidence * 100)}%)
              </span>
              <div className="muted">{suggestion.reasoning}</div>
            </div>
          )}
          <div className="mapping-grid">
            <label>Log name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} />

            <MappingSelect
              label="Case ID *"
              columns={preview.columns}
              value={mapping.case_id}
              onChange={(v) => setMapping({ ...mapping, case_id: v })}
            />
            <MappingSelect
              label="Activity *"
              columns={preview.columns}
              value={mapping.activity}
              onChange={(v) => setMapping({ ...mapping, activity: v })}
            />
            <MappingSelect
              label="Timestamp *"
              columns={preview.columns}
              value={mapping.timestamp}
              onChange={(v) => setMapping({ ...mapping, timestamp: v })}
            />
            {OPTIONAL_FIELDS.map((f) => (
              <MappingSelect
                key={f.key}
                label={f.label}
                columns={preview.columns}
                value={(mapping[f.key] as string) || ""}
                allowEmpty
                onChange={(v) => setMapping({ ...mapping, [f.key]: v || null })}
              />
            ))}
          </div>

          <h3>Preview (first {preview.rows.length} rows)</h3>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  {preview.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, i) => (
                  <tr key={i}>
                    {preview.columns.map((c) => (
                      <td key={c}>{row[c]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p style={{ marginTop: 16 }}>
            <button onClick={handleImport} disabled={!canImport}>
              {busy ? "Importing…" : "Import"}
            </button>
          </p>
        </>
      )}
    </div>
  );
}

function MappingSelect(props: {
  label: string;
  columns: string[];
  value: string;
  allowEmpty?: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <>
      <label>{props.label}</label>
      <select value={props.value} onChange={(e) => props.onChange(e.target.value)}>
        {props.allowEmpty && <option value="">— none —</option>}
        {!props.value && !props.allowEmpty && <option value="">— select —</option>}
        {props.columns.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    </>
  );
}

