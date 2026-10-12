// 前后端事件类型定义（与 backend/src/myopencode/core/events.py 对齐）

export type ClientEvent =
  | { type: "user_message"; session_id: string; content: string }
  | { type: "tool_approval"; id: string; decision: "once" | "always" | "reject" }
  | { type: "ask_user_reply"; id: string; answer: string }
  | { type: "safety_reply"; id: string; decision: "continue" | "abort" }
  | { type: "cancel"; session_id: string }
  | { type: "resume"; session_id: string }
  | { type: "config_update"; config: Record<string, unknown> };

export interface AssistantTextEvent {
  type: "assistant_text";
  delta: string;
  session_id?: string;
}

export interface ToolCallStartEvent {
  type: "tool_call_start";
  id: string;
  name: string;
  args: Record<string, unknown>;
  session_id?: string;
}

export interface ToolCallEndEvent {
  type: "tool_call_end";
  id: string;
  result: string;
  diff: string | null;
  session_id?: string;
}

export interface ApprovalRequestEvent {
  type: "approval_request";
  id: string;
  tool: string;
  args: Record<string, unknown>;
  message: string;
  session_id?: string;
}

export interface StateSnapshotEvent {
  type: "state_snapshot";
  state: Record<string, unknown>;
}

export interface IntentEvent {
  type: "intent";
  category: string;
  confidence: number;
  tool_names: string[] | null;
  needs_rag: boolean;
  reasoning: string;
  session_id?: string;
}

export interface PlanEvent {
  type: "plan";
  steps: { id: string; title: string; description: string; depends_on: string[] }[];
  session_id?: string;
}

export interface PlanStepEvent {
  type: "plan_step";
  step: { id: string; title: string };
  status: string;
  session_id?: string;
}

export interface ProgressEvent {
  type: "progress";
  stage: string;
  message: string;
  session_id?: string;
}

export interface AskUserEvent {
  type: "ask_user";
  id: string;
  question: string;
  options?: AskOption[];
  multi?: boolean;
  session_id?: string;
}

export interface AskOption {
  label: string;
  description?: string | null;
  recommended?: boolean;
}

export interface SafetyEvent {
  type: "safety";
  id: string;
  reasons: string[];
  severity: string;
  session_id?: string;
}

export interface ContentFlagEvent {
  type: "content_flag";
  message: string;
  session_id?: string;
}

export interface BudgetWarningEvent {
  type: "budget_warning";
  daily_spent: number;
  daily_budget: number | null;
  monthly_spent: number;
  monthly_budget: number | null;
  over: boolean;
  warning: boolean;
  hard_stop: boolean;
  session_id?: string;
}

export interface BudgetExceededEvent {
  type: "budget_exceeded";
  daily_spent: number;
  daily_budget: number | null;
  monthly_spent: number;
  monthly_budget: number | null;
  over: boolean;
  warning: boolean;
  hard_stop: boolean;
  session_id?: string;
}

export interface DegradedEvent {
  type: "degraded";
  message: string;
  detail?: unknown;
  session_id?: string;
}

export interface ReflectionEvent {
  type: "reflection";
  attempt: number;
  critique: string;
  session_id?: string;
}

export interface ErrorEvent {
  type: "error";
  message: string;
  code?: string;
}

export interface DoneEvent {
  type: "done";
  session_id?: string;
}

export type ServerEvent =
  | AssistantTextEvent
  | ToolCallStartEvent
  | ToolCallEndEvent
  | ApprovalRequestEvent
  | StateSnapshotEvent
  | IntentEvent
  | PlanEvent
  | PlanStepEvent
  | ProgressEvent
  | AskUserEvent
  | SafetyEvent
  | ContentFlagEvent
  | BudgetWarningEvent
  | BudgetExceededEvent
  | DegradedEvent
  | ReflectionEvent
  | ErrorEvent
  | DoneEvent;

// ── Thinking 时间线（思考过程可点击展开） ─────────────────────
export interface ThinkingEntry {
  id: string;
  kind: "intent" | "plan" | "plan_step" | "progress";
  title: string;
  detail?: string;
  status?: "pending" | "running" | "done" | "failed";
  stepId?: string;
}

// ── UI 消息模型 ────────────────────────────────────────────
export type ChatMessage =
  | { id: string; role: "user" | "assistant"; content: string; streaming?: boolean }
  | {
      id: string;
      role: "tool";
      name: string;
      args?: Record<string, unknown>;
      result?: string;
      diff?: string | null;
      status: "running" | "done" | "error" | "rejected";
    }
  | {
      id: string;
      role: "approval";
      tool: string;
      args: Record<string, unknown>;
      message: string;
      status: "pending" | "approved" | "rejected";
    }
  | {
      id: string;
      role: "ask_user";
      question: string;
      options?: AskOption[];
      multi?: boolean;
      status: "pending" | "answered";
      answer?: string;
    }
  | {
      id: string;
      role: "safety";
      reasons: string[];
      severity: string;
      status: "pending" | "allowed" | "blocked";
    }
  | {
      id: string;
      role: "content_flag";
      message: string;
    };