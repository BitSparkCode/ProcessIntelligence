import { useCallback, useEffect, useState } from "react";
import {
  clearToken,
  CurrentUser,
  EventLog,
  getMe,
  getToken,
  listLogs,
} from "./api";
import Auth from "./components/Auth";
import CsvImport from "./components/CsvImport";
import LogList from "./components/LogList";
import ProcessGraph from "./components/ProcessGraph";

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);
  const [logs, setLogs] = useState<EventLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<EventLog | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLogs(await listLogs());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  const loadSession = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setReady(true);
      return;
    }
    try {
      setUser(await getMe());
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  useEffect(() => {
    if (user) refresh();
  }, [user, refresh]);

  function signOut() {
    clearToken();
    setUser(null);
    setLogs([]);
    setActive(null);
  }

  if (!ready) return null;

  if (!user) {
    return (
      <div className="app">
        <header className="app-header">
          <h1>Process Intelligence</h1>
          <p className="muted">Open-source, AI-first process &amp; task mining</p>
        </header>
        <Auth onAuthenticated={loadSession} />
      </div>
    );
  }

  if (active) {
    return (
      <ProcessGraph
        logId={active.id}
        logName={active.name}
        onClose={() => setActive(null)}
      />
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Process Intelligence</h1>
          <p className="muted">Open-source, AI-first process &amp; task mining</p>
        </div>
        <div className="session">
          <span className="muted">{user.email}</span>
          <button className="secondary" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      <div className="card">
        <h2>Import event log (CSV)</h2>
        <CsvImport onImported={refresh} />
      </div>

      <div className="card">
        <h2>Event logs</h2>
        {error && <div className="error">{error}</div>}
        <LogList logs={logs} onChanged={refresh} onDiscover={setActive} />
      </div>
    </div>
  );
}
