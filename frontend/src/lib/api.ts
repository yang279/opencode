import { httpBase } from "./backend";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = await httpBase();
  const res = await fetch(`${base}${path}`, init);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) {
        msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export interface HealthInfo {
  status: string;
  version: string;
  provider: string;
  available_providers: string[];
}

export interface TreeEntry {
  path: string;
  type: "file" | "dir";
}

export interface ProviderConfig {
  api_key?: string | null;
  base_url?: string | null;
  model?: string | null;
  extra?: Record<string, unknown>;
}

export interface PermissionsConfig {
  allow_commands: string[];
  deny_commands: string[];
  allow_all_commands: boolean;
  require_approval_for_write: boolean;
  require_approval_for_shell: boolean;
}

export interface IntentConfig {
  enabled: boolean;
  provider?: string | null;
  model?: string | null;
  api_key?: string | null;
  base_url?: string | null;
  semantic_enabled?: boolean;
  tool_enabled?: boolean;
  gate_destructive?: boolean;
  timeout?: number;
  temperature?: number;
  max_tokens?: number;
  disable_thinking?: boolean;
}

export interface ContainerSandboxConfig {
  image?: string;
  cpus?: number | null;
  memory?: string;
  runtime?: string;
}

export interface SandboxConfig {
  enabled: boolean;
  backend?: string;
  allow_network: boolean;
  container?: ContainerSandboxConfig;
  extra_read_paths?: string[];
  extra_write_paths?: string[];
  deny_write_outside_workspace?: boolean;
}

export interface BackupConfig {
  enabled: boolean;
  retain_on_success?: boolean;
}

export interface PlanningConfig {
  enabled: boolean;
  max_steps?: number;
  allow_parallel?: boolean;
  max_parallel?: number;
  verify?: boolean;
  max_retries?: number;
  verify_command?: string | null;
}

export interface LlmConfig {
  fallback_providers?: string[];
  pricing?: Record<string, Record<string, number>>;
  daily_budget_usd?: number | null;
  monthly_budget_usd?: number | null;
  per_request_max_tokens?: number | null;
  budget_hard_stop?: boolean;
}

export interface AppConfig {
  provider: string;
  model: string | null;
  providers: Record<string, ProviderConfig>;
  working_dir: string;
  permissions: PermissionsConfig;
  system_prompt: string | null;
  mcp_servers?: Record<string, unknown>;
  intent?: IntentConfig;
  sandbox?: SandboxConfig;
  backup?: BackupConfig;
  planning?: PlanningConfig;
  llm?: LlmConfig;
}

export interface SkillMeta {
  name: string;
  description: string;
  source: string;
}

export interface ToolMeta {
  name: string;
  description: string;
}

export interface SessionMeta {
  id: string;
  title: string;
  message_count: number;
  resumable?: boolean;
  tokens_in?: number;
  tokens_out?: number;
}

export interface MessageRecord {
  role: string;
  content: string;
  tool_calls?: unknown[];
  tool_call_id?: string;
  name?: string;
}

export interface SessionMessages {
  id: string;
  title: string;
  messages: MessageRecord[];
}

export interface UsageSummary {
  budget: {
    daily_spent: number;
    daily_budget: number | null;
    monthly_spent: number;
    monthly_budget: number | null;
    over: boolean;
    warning: boolean;
    hard_stop: boolean;
  };
  today: { tokens_in: number; tokens_out: number; cost: number };
  this_month: { tokens_in: number; tokens_out: number; cost: number };
  by_model_today: Record<string, { tokens_in: number; tokens_out: number; cost: number }>;
}

export interface Diagnostics {
  status: string;
  version: string;
  provider: {
    name: string;
    model: string | null;
    configured: boolean;
    fallbacks: string[];
  };
  sandbox: { enabled: boolean; backend: string; allow_network: boolean };
  mcp: { configured: string[]; connected: string[] };
  features: Record<string, boolean>;
  metrics: { counters: Record<string, number> };
  process: { maxrss_bytes: number | null };
  disk: { logs: number | null; audit: number | null };
}

export interface TraceSpan {
  name: string;
  span_id: string;
  parent_span_id: string | null;
  trace_id: string | null;
  session_id: string | null;
  started_at_ms: number;
  duration_ms: number;
  attrs: Record<string, unknown>;
}

export const api = {
  health: () => request<HealthInfo>("/health"),
  getConfig: () => request<AppConfig>("/config"),
  updateConfig: (config: AppConfig) =>
    request<{ ok: boolean; config: AppConfig; saved_to: string }>("/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  workspaceTree: () => request<{ root: string; entries: TreeEntry[] }>("/workspace/tree"),
  readFile: (path: string) =>
    request<{ path: string; content?: string; error?: string }>(
      `/workspace/file?path=${encodeURIComponent(path)}`,
    ),
  getSkills: () => request<SkillMeta[]>("/skills"),
  getTools: () => request<ToolMeta[]>("/tools"),
  listSessions: () => request<SessionMeta[]>("/sessions"),
  createSession: () =>
    request<{ id: string; title: string }>("/sessions", { method: "POST" }),
  deleteSession: (id: string) =>
    request<{ ok: boolean }>(`/sessions/${id}`, { method: "DELETE" }),
  getMessages: (id: string) => request<SessionMessages>(`/sessions/${id}/messages`),
  undo: (id: string) =>
    request<{ ok: boolean; restored: string[] }>(`/sessions/${id}/undo`, {
      method: "POST",
    }),
  getUsageSummary: () => request<UsageSummary>("/usage/summary"),
  getDiagnostics: () => request<Diagnostics>("/diagnostics"),
  getTraces: (sessionId?: string) =>
    request<{ spans: TraceSpan[] }>(
      `/traces${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`,
    ),
  diagnosticsExportUrl: async () => `${await httpBase()}/diagnostics/export`,
};