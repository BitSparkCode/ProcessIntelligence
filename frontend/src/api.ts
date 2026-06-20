export interface CsvPreview {
  columns: string[];
  rows: Record<string, string>[];
  total_preview_rows: number;
}

export interface SuggestedColumnMapping {
  case_id?: string | null;
  activity?: string | null;
  timestamp?: string | null;
  resource?: string | null;
  cost?: string | null;
  lifecycle?: string | null;
  timestamp_format?: string | null;
}

export interface MappingSuggestion {
  mapping: SuggestedColumnMapping;
  confidence: number;
  reasoning: string;
  source: "heuristic" | "ai";
  ai_enabled: boolean;
}

export interface UploadResponse {
  upload_id: string;
  preview: CsvPreview;
  suggestion: MappingSuggestion;
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

export interface ActivityNode {
  id: string;
  label: string;
  frequency: number;
  is_start: boolean;
  is_end: boolean;
  avg_duration_seconds: number | null;
}

export interface ProcessEdge {
  source: string;
  target: string;
  frequency: number;
  dependency: number;
  avg_duration_seconds: number;
}

export interface ProcessGraph {
  log_id: string;
  algorithm: string;
  nodes: ActivityNode[];
  edges: ProcessEdge[];
  case_count: number;
  event_count: number;
  start_activities: string[];
  end_activities: string[];
  dependency_threshold: number;
  frequency_threshold: number;
}

export interface DiscoveryParams {
  dependency_threshold: number;
  frequency_threshold: number;
}

export interface Variant {
  rank: number;
  sequence: string[];
  case_count: number;
  percentage: number;
  avg_throughput_seconds: number;
}

export interface VariantReport {
  log_id: string;
  case_count: number;
  variant_count: number;
  variants: Variant[];
}

export interface VariantParams {
  top_n?: number | null;
  min_frequency?: number;
}

export interface ActivityStat {
  activity: string;
  frequency: number;
  avg_duration_to_next_seconds: number | null;
}

export interface TransitionStat {
  source: string;
  target: string;
  frequency: number;
  avg_waiting_seconds: number;
}

export interface HistogramBin {
  lower_seconds: number;
  upper_seconds: number;
  count: number;
}

export interface PerformanceReport {
  log_id: string;
  case_count: number;
  event_count: number;
  avg_throughput_seconds: number;
  median_throughput_seconds: number;
  min_throughput_seconds: number;
  max_throughput_seconds: number;
  activity_stats: ActivityStat[];
  transition_stats: TransitionStat[];
  histogram: HistogramBin[];
  window_days: number | null;
}

export interface PerformanceParams {
  window_days?: number | null;
  histogram_bins?: number;
}

export interface CurrentUser {
  id: string;
  email: string;
  workspace_id: string;
}

const TOKEN_KEY = "pi_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = getToken();
  return {
    ...(extra ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    if (resp.status === 401) clearToken();
    let detail: unknown;
    try {
      detail = (await resp.json()).detail;
    } catch {
      detail = resp.statusText;
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export async function register(email: string, password: string): Promise<string> {
  const resp = await handle<{ access_token: string }>(
    await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  );
  setToken(resp.access_token);
  return resp.access_token;
}

export async function login(email: string, password: string): Promise<string> {
  const resp = await handle<{ access_token: string }>(
    await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  );
  setToken(resp.access_token);
  return resp.access_token;
}

export async function getMe(): Promise<CurrentUser> {
  return handle<CurrentUser>(await fetch("/api/auth/me", { headers: authHeaders() }));
}

export async function uploadCsv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return handle<UploadResponse>(
    await fetch("/api/logs/upload", {
      method: "POST",
      headers: authHeaders(),
      body: form,
    }),
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
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ upload_id: uploadId, name, mapping }),
    }),
  );
}

export async function listLogs(): Promise<EventLog[]> {
  return handle<EventLog[]>(await fetch("/api/logs", { headers: authHeaders() }));
}

export async function deleteLog(id: string): Promise<void> {
  return handle<void>(
    await fetch(`/api/logs/${id}`, { method: "DELETE", headers: authHeaders() }),
  );
}

export async function discoverHeuristicMiner(
  logId: string,
  params: DiscoveryParams,
): Promise<ProcessGraph> {
  return handle<ProcessGraph>(
    await fetch(`/api/discovery/${logId}/heuristic-miner`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(params),
    }),
  );
}

export async function discoverInductiveMiner(
  logId: string,
): Promise<ProcessGraph> {
  return handle<ProcessGraph>(
    await fetch(`/api/discovery/${logId}/inductive-miner`, {
      method: "POST",
      headers: authHeaders(),
    }),
  );
}

export async function downloadBpmn(logId: string, logName: string): Promise<void> {
  const resp = await fetch(`/api/discovery/${logId}/bpmn`, {
    headers: authHeaders(),
  });
  if (!resp.ok) {
    if (resp.status === 401) clearToken();
    throw new Error(`BPMN export failed (${resp.status})`);
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${logName || "process"}.bpmn`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function analyzeVariants(
  logId: string,
  params: VariantParams,
): Promise<VariantReport> {
  return handle<VariantReport>(
    await fetch(`/api/analysis/${logId}/variants`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(params),
    }),
  );
}

export async function analyzePerformance(
  logId: string,
  params: PerformanceParams,
): Promise<PerformanceReport> {
  return handle<PerformanceReport>(
    await fetch(`/api/analysis/${logId}/performance`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(params),
    }),
  );
}
