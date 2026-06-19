export interface CsvPreview {
  columns: string[];
  rows: Record<string, string>[];
  total_preview_rows: number;
}

export interface UploadResponse {
  upload_id: string;
  preview: CsvPreview;
}

export interface ColumnMapping {
  case_id: string;
  activity: string;
  timestamp: string;
  resource?: string | null;
  cost?: string | null;
  lifecycle?: string | null;
  timestamp_format?: string | null;
}

export interface ImportResult {
  log_id: string;
  name: string;
  row_count: number;
  case_count: number;
  activity_count: number;
}

export interface EventLog {
  id: string;
  name: string;
  source: string;
  imported_at: string;
  row_count: number;
  case_count: number;
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = (await resp.json()).detail;
    } catch {
      detail = resp.statusText;
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return resp.json() as Promise<T>;
}

export async function uploadCsv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return handle<UploadResponse>(
    await fetch("/api/logs/upload", { method: "POST", body: form }),
  );
}

export async function importCsv(
  uploadId: string,
  name: string,
  mapping: ColumnMapping,
): Promise<ImportResult> {
  return handle<ImportResult>(
    await fetch("/api/logs/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: uploadId, name, mapping }),
    }),
  );
}

export async function listLogs(): Promise<EventLog[]> {
  return handle<EventLog[]>(await fetch("/api/logs"));
}

export async function deleteLog(id: string): Promise<void> {
  const resp = await fetch(`/api/logs/${id}`, { method: "DELETE" });
  if (!resp.ok) throw new Error("Failed to delete log");
}
