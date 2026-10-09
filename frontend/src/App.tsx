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
import XesImport from "./components/XesImport";

type Section = "logs" | "import";

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);
  const [logs, setLogs] = useState<EventLog[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<EventLog | null>(null);
  const [section, setSection] = useState<Section>("logs");

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
      <div className="auth-shell">
        <div className="auth-brand">
          <span className="brand-mark">π</span>
          <h1>Process Intelligence</h1>
          <p className="muted">
            Open-source process mining — discover, analyse and simulate.
          </p>
        </div>
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
    <div className="shell">
      <nav className="rail">
        <div className="rail__brand">π</div>
        <button
          className={`rail__item${section === "logs" ? " active" : ""}`}
          onClick={() => setSection("logs")}
          title="Event logs"
        >
          <span className="rail__icon">▤</span>
          Logs
        </button>
        <button
          className={`rail__item${section === "import" ? " active" : ""}`}
          onClick={() => setSection("import")}
          title="Import data"
        >
          <span className="rail__icon">⇪</span>
          Import
        </button>
        <div className="rail__spacer" />
        <button className="rail__item" onClick={signOut} title={user.email}>
          <span className="rail__icon">⏻</span>
          Sign out
        </button>
      </nav>

      <main className="main">
        <header className="main-header">
          <h1>{section === "logs" ? "Event logs" : "Import data"}</h1>
          <p className="muted">
            {section === "logs"
              ? `${logs.length} log${logs.length === 1 ? "" : "s"} in your workspace`
              : "Upload an event log — AI assists with column mapping and data cleaning."}
          </p>
        </header>

        {section === "import" && (
          <>
            <div className="card">
              <h2>CSV</h2>
              <CsvImport
                onImported={() => {
                  refresh();
                  setSection("logs");
                }}
              />
            </div>
            <div className="card">
              <h2>XES</h2>
              <p className="muted">
                Upload a standard .xes or .xes.gz file — no column mapping
                needed.
              </p>
              <XesImport
                onImported={() => {
                  refresh();
                  setSection("logs");
                }}
              />
            </div>
          </>
        )}

        {section === "logs" && (
          <div className="card">
            {error && <div className="error">{error}</div>}
            <LogList logs={logs} onChanged={refresh} onDiscover={setActive} />
          </div>
        )}
      </main>
    </div>
  );
}
