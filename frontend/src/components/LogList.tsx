import { EventLog, deleteLog } from "../api";

interface Props {
  logs: EventLog[];
  onChanged: () => void;
  onDiscover: (log: EventLog) => void;
}

export default function LogList({ logs, onChanged, onDiscover }: Props) {
  async function handleDelete(id: string) {
    if (!confirm("Delete this log and all derived data?")) return;
    await deleteLog(id);
    onChanged();
  }

  if (logs.length === 0) {
    return <p className="muted">No event logs imported yet.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Source</th>
          <th>Events</th>
          <th>Cases</th>
          <th>Imported</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {logs.map((log) => (
          <tr key={log.id}>
            <td>{log.name}</td>
            <td>{log.source}</td>
            <td>{log.row_count.toLocaleString()}</td>
            <td>{log.case_count.toLocaleString()}</td>
            <td>{new Date(log.imported_at).toLocaleString()}</td>
            <td className="row-actions">
              <button onClick={() => onDiscover(log)}>Discover</button>
              <button className="secondary" onClick={() => handleDelete(log.id)}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
