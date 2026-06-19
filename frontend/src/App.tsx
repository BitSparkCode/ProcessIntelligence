import { useCallback, useEffect, useState } from "react";
import { EventLog, listLogs } from "./api";
import CsvImport from "./components/CsvImport";
import LogList from "./components/LogList";

export default function App() {
  const [logs, setLogs] = useState<EventLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLogs(await listLogs());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="app">
      <h1>Process Intelligence</h1>
      <p className="muted">Open-source process &amp; task mining — MVP</p>

      <div className="card">
        <h2>Import event log (CSV)</h2>
        <CsvImport onImported={refresh} />
      </div>

      <div className="card">
        <h2>Event logs</h2>
        {error && <div className="error">{error}</div>}
        <LogList logs={logs} onChanged={refresh} />
      </div>
    </div>
  );
}
