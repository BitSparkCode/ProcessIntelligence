import { useRef, useState } from "react";
import { importXes } from "../api";

interface Props {
  onImported: () => void;
}

export default function XesImport({ onImported }: Props) {
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFile(f: File) {
    setFile(f);
    setName(f.name.replace(/\.xes(\.gz)?$/i, ""));
    setError(null);
    setSuccess(null);
  }

  async function handleImport() {
    if (!file) return;
    setError(null);
    setSuccess(null);
    setBusy(true);
    try {
      const result = await importXes(file, name || "XES log");
      setSuccess(
        `Imported "${result.name}": ${result.row_count} events, ` +
          `${result.case_count} cases, ${result.activity_count} activities.`,
      );
      setFile(null);
      setName("");
      if (inputRef.current) inputRef.current.value = "";
      onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept=".xes,.xes.gz"
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        disabled={busy}
      />
      {file && (
        <div className="mapping-grid" style={{ marginTop: 8 }}>
          <label>Log name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
      )}
      {error && <div className="error">{error}</div>}
      {success && <div className="success">{success}</div>}
      {file && (
        <p style={{ marginTop: 8 }}>
          <button onClick={handleImport} disabled={busy || !file}>
            {busy ? "Importing…" : "Import XES"}
          </button>
        </p>
      )}
    </div>
  );
}
