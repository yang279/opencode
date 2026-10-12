import { useCallback, useEffect, useRef, useState } from "react";
import { WsClient } from "../lib/wsClient";
import { api, type MessageRecord, type SessionMeta } from "../lib/api";
import type { ChatMessage, ThinkingEntry } from "../types/events";

export interface TerminalLine {
  id: string;
  kind: "cmd" | "out" | "err" | "info";
  text: string;
}

let seq = 0;
const genId = () => `m${Date.now()}_${seq++}`;

function recordToChatMessages(records: MessageRecord[]): ChatMessage[] {
  const out: ChatMessage[] = [];
  for (const r of records) {
    if (r.role === "user") {
      out.push({ id: genId(), role: "user", content: r.content });
    } else if (r.role === "assistant" && r.content) {
      out.push({ id: genId(), role: "assistant", content: r.content });
    } else if (r.role === "tool") {
      out.push({ id: genId(), role: "tool", name: r.name ?? "tool", result: r.content, status: "done" });
    }
  }
  return out;
}

export function useAgent() {
  const clientRef = useRef<WsClient | null>(null);
  const streamingBySessionRef = useRef<Record<string, string | null>>({});
  const runningSessionsRef = useRef<Set<string>>(new Set());
  const loadedRef = useRef<Set<string>>(new Set());
  const initRef = useRef(false);

  const [connected, setConnected] = useState(false);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messagesBySession, setMessagesBySession] = useState<Record<string, ChatMessage[]>>({});
  const [thinkingBySession, setThinkingBySession] = useState<Record<string, ThinkingEntry[]>>({});
  const [runningBySession, setRunningBySession] = useState<Record<string, boolean>>({});
  const [terminal, setTerminal] = useState<TerminalLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [degraded, setDegraded] = useState<string | null>(null);

  const running = activeSessionId ? (runningBySession[activeSessionId] ?? false) : false;

  const messages: ChatMessage[] =
    activeSessionId ? (messagesBySession[activeSessionId] ?? []) : [];

  const thinking: ThinkingEntry[] =
    activeSessionId ? (thinkingBySession[activeSessionId] ?? []) : [];

  const resumable =
    activeSessionId != null
      ? (sessions.find((s) => s.id === activeSessionId)?.resumable ?? false)
      : false;

  const pushTerminal = useCallback(
    (kind: TerminalLine["kind"], text: string) => {
      setTerminal((prev) => [...prev.slice(-499), { id: genId(), kind, text }]);
    },
    [],
  );

  const appendToSession = useCallback(
    (sid: string, updater: (prev: ChatMessage[]) => ChatMessage[]) => {
      setMessagesBySession((prev) => ({
        ...prev,
        [sid]: updater(prev[sid] ?? []),
      }));
    },
    [],
  );

  const appendThinking = useCallback(
    (sid: string, updater: (prev: ThinkingEntry[]) => ThinkingEntry[]) => {
      setThinkingBySession((prev) => ({
        ...prev,
        [sid]: updater(prev[sid] ?? []),
      }));
    },
    [],
  );

  const setSessionRunning = useCallback((sid: string, v: boolean) => {
    setRunningBySession((prev) => {
      if (v === (prev[sid] ?? false)) return prev;
      return { ...prev, [sid]: v };
    });
    if (v) runningSessionsRef.current.add(sid);
    else runningSessionsRef.current.delete(sid);
  }, []);

  const dispatchMessage = useCallback(
    (content: string, sid: string) => {
      const text = content.trim();
      if (!text || !sid) return;
      streamingBySessionRef.current[sid] = null;
      setError(null);
      setThinkingBySession((prev) => ({ ...prev, [sid]: [] }));
      appendToSession(sid, (prev) => [
        ...prev,
        { id: genId(), role: "user", content: text },
      ]);
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sid && (!s.title || s.title === "新对话")
            ? { ...s, title: text.slice(0, 30) }
            : s,
        ),
      );
      setSessionRunning(sid, true);
      clientRef.current?.send({ type: "user_message", session_id: sid, content: text });
    },
    [appendToSession, setSessionRunning],
  );

  // ── WS 连接 + 事件归档 ──────────────────────────────────
  useEffect(() => {
    const client = new WsClient();
    clientRef.current = client;

    let wasConnected = false;
    client.setStatusHandler((status) => {
      if (status === "connected") {
        setConnected(true);
        if (wasConnected) pushTerminal("info", "已重新连接后端");
        wasConnected = true;
      } else if (status === "disconnected") {
        setConnected(false);
        if (wasConnected) pushTerminal("err", "后端连接断开，自动重连中…");
      }
    });

    client.on("assistant_text", (ev) => {
      if (ev.type !== "assistant_text") return;
      const sid = ev.session_id;
      if (!sid) return;
      const existing = streamingBySessionRef.current[sid] ?? null;
      if (existing === null) {
        const newId = genId();
        streamingBySessionRef.current[sid] = newId;
        appendToSession(sid, (prev) => [
          ...prev,
          { id: newId, role: "assistant", content: ev.delta, streaming: true },
        ]);
      } else {
        appendToSession(sid, (prev) =>
          prev.map((m) =>
            m.id === existing && m.role === "assistant"
              ? { ...m, content: m.content + ev.delta }
              : m,
          ),
        );
      }
    });

    client.on("tool_call_start", (ev) => {
      if (ev.type !== "tool_call_start") return;
      const sid = ev.session_id;
      if (!sid) return;
      streamingBySessionRef.current[sid] = null;
      appendToSession(sid, (prev) => [
        ...prev,
        { id: ev.id, role: "tool", name: ev.name, args: ev.args, status: "running" },
      ]);
    });

    client.on("tool_call_end", (ev) => {
      if (ev.type !== "tool_call_end") return;
      const rejected = ev.result.includes("用户拒绝");
      const sid = ev.session_id ?? activeSessionId;
      if (sid) {
        appendToSession(sid, (prev) =>
          prev.map((m) =>
            m.id === ev.id && m.role === "tool"
              ? { ...m, result: ev.result, diff: ev.diff ?? null, status: rejected ? "rejected" : "done" }
              : m,
          ),
        );
      }
      pushTerminal(ev.result.includes("错误") || rejected ? "err" : "out", ev.result);
    });

    client.on("approval_request", (ev) => {
      if (ev.type !== "approval_request") return;
      const sid = ev.session_id;
      if (!sid) return;
      appendToSession(sid, (prev) => [
        ...prev,
        { id: ev.id, role: "approval", tool: ev.tool, args: ev.args, message: ev.message, status: "pending" },
      ]);
    });

    client.on("ask_user", (ev) => {
      if (ev.type !== "ask_user") return;
      const sid = ev.session_id;
      if (!sid) return;
      appendToSession(sid, (prev) => [
        ...prev,
        {
          id: ev.id,
          role: "ask_user",
          question: ev.question,
          options: ev.options,
          multi: ev.multi,
          status: "pending",
        },
      ]);
    });

    client.on("safety", (ev) => {
      if (ev.type !== "safety") return;
      const sid = ev.session_id;
      if (!sid) return;
      appendToSession(sid, (prev) => [
        ...prev,
        { id: ev.id, role: "safety", reasons: ev.reasons, severity: ev.severity, status: "pending" },
      ]);
    });

    client.on("content_flag", (ev) => {
      if (ev.type !== "content_flag") return;
      const sid = ev.session_id;
      if (!sid) return;
      appendToSession(sid, (prev) => [
        ...prev,
        { id: genId(), role: "content_flag", message: ev.message },
      ]);
    });

    client.on("budget_warning", (ev) => {
      if (ev.type !== "budget_warning") return;
      const day = ev.daily_budget != null ? `本日 $${ev.daily_spent.toFixed(4)} / $${ev.daily_budget.toFixed(2)}` : "";
      const month = ev.monthly_budget != null ? `本月 $${ev.monthly_spent.toFixed(4)} / $${ev.monthly_budget.toFixed(2)}` : "";
      pushTerminal("info", `预算告警：${[day, month].filter(Boolean).join("，") || "接近预算上限"}`);
    });

    client.on("budget_exceeded", (ev) => {
      if (ev.type !== "budget_exceeded") return;
      pushTerminal("err", "预算超限，任务已停止");
      setError("预算超限，本次任务已停止");
    });

    client.on("degraded", (ev) => {
      if (ev.type !== "degraded") return;
      setDegraded(ev.message);
      pushTerminal("err", `降级提示：${ev.message}`);
    });

    client.on("reflection", (ev) => {
      if (ev.type !== "reflection") return;
      const sid = ev.session_id;
      const title = `反思 #${ev.attempt}`;
      if (sid) {
        appendThinking(sid, (prev) => [
          ...prev.map((e) =>
            e.kind === "progress" && e.status === "running" ? { ...e, status: "done" as const } : e,
          ),
          { id: genId(), kind: "progress", title, detail: ev.critique, status: "done" },
        ]);
      }
      pushTerminal("info", `${title}: ${ev.critique || "重试中"}`);
    });

    const intentLabels: Record<string, string> = {
      code_edit: "修改代码",
      code_read: "阅读代码",
      explore: "搜索代码",
      execute: "执行命令",
      question: "问答",
      plan: "规划",
      compose: "内容创作",
      chat: "闲聊",
    };

    client.on("plan", (ev) => {
      if (ev.type !== "plan") return;
      const sid = ev.session_id;
      if (sid) {
        appendThinking(sid, (prev) => [
          ...prev,
          ...ev.steps.map((s) => ({
            id: genId(),
            kind: "plan" as const,
            title: s.title,
            detail: s.description,
            status: "pending" as const,
            stepId: s.id,
          })),
        ]);
      }
      const titles = ev.steps.map((s) => s.title).join(" → ");
      pushTerminal("info", `计划: ${ev.steps.length} 步（${titles}）`);
    });

    client.on("plan_step", (ev) => {
      if (ev.type !== "plan_step") return;
      const sid = ev.session_id;
      const status: ThinkingEntry["status"] =
        ev.status === "done" ? "done" : ev.status === "running" ? "running" : "failed";
      if (sid) {
        appendThinking(sid, (prev) =>
          prev.map((e) =>
            e.stepId === ev.step.id
              ? { ...e, title: ev.step.title, status }
              : e,
          ),
        );
      }
      pushTerminal(
        ev.status === "failed" ? "err" : "out",
        `[步骤] ${ev.step.title} · ${ev.status === "done" ? "完成" : ev.status === "running" ? "执行中" : "失败"}`,
      );
    });

    client.on("progress", (ev) => {
      if (ev.type !== "progress") return;
      const sid = ev.session_id;
      if (!sid) return;
      appendThinking(sid, (prev) => {
        const settled = prev.map((e) =>
          e.kind === "progress" && e.status === "running" ? { ...e, status: "done" as const } : e,
        );
        return [
          ...settled,
          { id: genId(), kind: "progress", title: ev.message, status: "running" },
        ];
      });
    });

    client.on("intent", (ev) => {
      if (ev.type !== "intent") return;
      const label = intentLabels[ev.category] ?? ev.category;
      const pruned = ev.tool_names ? `工具${ev.tool_names.length}个` : "全量工具";
      const sid = ev.session_id;
      if (sid) {
        appendThinking(sid, (prev) => [
          ...prev,
          {
            id: genId(),
            kind: "intent",
            title: "意图识别",
            detail: `${label} · 置信度 ${ev.confidence.toFixed(2)} · ${pruned}${
              ev.reasoning ? ` · ${ev.reasoning}` : ""
            }`,
            status: "done",
          },
        ]);
      }
      pushTerminal("info", `意图识别: ${label} (置信度 ${ev.confidence.toFixed(2)}，${pruned})`);
    });

    client.on("error", (ev) => {
      if (ev.type !== "error") return;
      const hints: Record<string, string> = {
        BUDGET_EXCEEDED: "请调高预算上限或等待次日重置",
        LLM_AUTH: "请检查 API Key 是否正确",
        LLM_TIMEOUT: "网络或服务响应过慢，请稍后重试",
        NO_PROVIDER: "未配置可用的模型 provider",
        SANDBOX_UNAVAILABLE: "沙箱不可用，已降级到 pathguard",
      };
      const hint = ev.code ? hints[ev.code] : undefined;
      setError(hint ? `${ev.message}（${hint}）` : ev.message);
      pushTerminal("err", ev.message);
    });

    client.on("done", (ev) => {
      if (ev.type !== "done") return;
      const sid = ev.session_id;
      if (sid) {
        setSessionRunning(sid, false);
        streamingBySessionRef.current[sid] = null;
        appendToSession(sid, (prev) =>
          prev.map((m) =>
            m.role === "assistant" && m.streaming ? { ...m, streaming: false } : m,
          ),
        );
      }
      api
        .listSessions()
        .then((fetched) => {
          setSessions((prev) => {
            const byId = new Map(fetched.map((f) => [f.id, f]));
            const merged = prev.map((s) => (byId.has(s.id) ? { ...s, ...byId.get(s.id)! } : s));
            for (const f of fetched) {
              if (!prev.some((s) => s.id === f.id)) merged.push(f);
            }
            return merged;
          });
        })
        .catch(() => {});
    });

    client.connect();

    return () => client.close();
  }, [appendToSession, appendThinking, pushTerminal, setSessionRunning]);

  // ── 初始化会话列表 ──────────────────────────────────────
  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    (async () => {
      try {
        let list = await api.listSessions();
        if (list.length === 0) {
          const created = await api.createSession();
          list = [{ id: created.id, title: created.title, message_count: 0 }];
        }
        setSessions(list);
        const firstId = list[0].id;
        setActiveSessionId(firstId);
        loadedRef.current.add(firstId);
        const data = await api.getMessages(firstId);
        setMessagesBySession({ [firstId]: recordToChatMessages(data.messages) });
      } catch (e) {
        setError(String(e));
      }
    })();
  }, []);

  // ── 会话操作 ────────────────────────────────────────────
  const switchSession = useCallback((id: string) => {
    setActiveSessionId(id);
    if (!loadedRef.current.has(id)) {
      loadedRef.current.add(id);
      api
        .getMessages(id)
        .then((data) => setMessagesBySession((prev) => ({ ...prev, [id]: recordToChatMessages(data.messages) })))
        .catch(() => {});
    }
  }, []);

  const createSessionAndActivate = useCallback(async () => {
    try {
      const created = await api.createSession();
      const meta: SessionMeta = { id: created.id, title: created.title, message_count: 0 };
      setSessions((prev) => [meta, ...prev]);
      setActiveSessionId(created.id);
      loadedRef.current.add(created.id);
      setMessagesBySession((prev) => ({ ...prev, [created.id]: [] }));
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const newSession = useCallback(async () => {
    const current = activeSessionId ? (messagesBySession[activeSessionId] ?? []) : [];
    if (current.length === 0) return;
    await createSessionAndActivate();
  }, [activeSessionId, messagesBySession, createSessionAndActivate]);

  const deleteSession = useCallback(
    async (id: string) => {
      try {
        await api.deleteSession(id);
        const remaining = sessions.filter((s) => s.id !== id);
        setSessions(remaining);
        setMessagesBySession((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
        loadedRef.current.delete(id);
        if (activeSessionId === id) {
          if (remaining.length > 0) {
            switchSession(remaining[0].id);
          } else {
            await createSessionAndActivate();
          }
        }
      } catch (e) {
        setError(String(e));
      }
    },
    [sessions, activeSessionId, switchSession, createSessionAndActivate],
  );

  // ── 消息/审批/取消 ──────────────────────────────────────
  const sendMessage = useCallback(
    (content: string): boolean => {
      const text = content.trim();
      if (!text || !activeSessionId) return false;
      if (text === "/undo" || text.startsWith("/undo ")) {
        api
          .undo(activeSessionId)
          .then((r) => {
            const n = r.restored.length;
            pushTerminal(
              "info",
              n > 0 ? `已回退 ${n} 个文件：${r.restored.join(", ")}` : "没有可回退的改动",
            );
          })
          .catch((e) => pushTerminal("err", String(e)));
        return true;
      }
      if (runningSessionsRef.current.has(activeSessionId)) {
        pushTerminal("err", "任务执行中，请先停止当前任务");
        return false;
      }
      dispatchMessage(text, activeSessionId);
      return true;
    },
    [activeSessionId, pushTerminal, dispatchMessage],
  );

  const resume = useCallback(() => {
    if (!activeSessionId) return;
    setSessionRunning(activeSessionId, true);
    clientRef.current?.send({ type: "resume", session_id: activeSessionId });
  }, [activeSessionId, setSessionRunning]);

  const respondApproval = useCallback((id: string, decision: "once" | "always" | "reject") => {
    clientRef.current?.send({ type: "tool_approval", id, decision });
    setMessagesBySession((prev) => {
      const next: Record<string, ChatMessage[]> = {};
      for (const sid of Object.keys(prev)) {
        next[sid] = (prev[sid] ?? []).map((m) =>
          m.id === id && m.role === "approval"
            ? { ...m, status: decision === "reject" ? "rejected" : "approved" }
            : m,
        );
      }
      return next;
    });
  }, []);

  const respondSafety = useCallback((id: string, decision: "continue" | "abort") => {
    clientRef.current?.send({ type: "safety_reply", id, decision });
    setMessagesBySession((prev) => {
      const next: Record<string, ChatMessage[]> = {};
      for (const sid of Object.keys(prev)) {
        next[sid] = (prev[sid] ?? []).map((m) =>
          m.id === id && m.role === "safety"
            ? { ...m, status: decision === "continue" ? "allowed" : "blocked" }
            : m,
        );
      }
      return next;
    });
  }, []);

  const respondAnswer = useCallback((id: string, answer: string) => {
    const text = answer.trim();
    if (!text) return;
    clientRef.current?.send({ type: "ask_user_reply", id, answer: text });
    setMessagesBySession((prev) => {
      const next: Record<string, ChatMessage[]> = {};
      for (const sid of Object.keys(prev)) {
        next[sid] = (prev[sid] ?? []).map((m) =>
          m.id === id && m.role === "ask_user"
            ? { ...m, status: "answered", answer: text }
            : m,
        );
      }
      return next;
    });
  }, []);

  const cancel = useCallback(() => {
    const sid = activeSessionId;
    if (!sid) return;
    clientRef.current?.send({ type: "cancel", session_id: sid });
    streamingBySessionRef.current[sid] = null;
    setSessionRunning(sid, false);
    appendToSession(sid, (prev) =>
      prev.map((m) => {
        if (m.role === "assistant" && m.streaming) return { ...m, streaming: false };
        if (m.role === "tool" && m.status === "running") return { ...m, status: "error" };
        if (m.role === "approval" && m.status === "pending") return { ...m, status: "rejected" };
        if (m.role === "ask_user" && m.status === "pending") return { ...m, status: "answered", answer: "(已取消)" };
        if (m.role === "safety" && m.status === "pending") return { ...m, status: "blocked" };
        return m;
      }),
    );
  }, [activeSessionId, setSessionRunning, appendToSession]);

  return {
    connected,
    running,
    messages,
    thinking,
    sessions,
    activeSessionId,
    resumable,
    terminal,
    error,
    degraded,
    sendMessage,
    respondApproval,
    respondAnswer,
    respondSafety,
    cancel,
    resume,
    clearError: () => setError(null),
    clearDegraded: () => setDegraded(null),
    newSession,
    switchSession,
    deleteSession,
  };
}
