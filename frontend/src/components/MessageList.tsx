import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button, Collapse, Input, Space, Tag, Typography } from "antd";
import {
  BulbOutlined,
  LoadingOutlined,
  UserOutlined,
  RobotOutlined,
  CheckOutlined,
  CloseOutlined,
  WarningOutlined,
  QuestionCircleOutlined,
  PaperClipOutlined,
} from "@ant-design/icons";
import type { Attachment, ChatMessage, ThinkingEntry } from "../types/events";
import logo from "../assets/icon.png";

function Diff({ diff }: { diff: string }) {
  if (!diff) return null;
  const lines = diff.split("\n");
  return (
    <div className="diff-view">
      {lines.map((l, i) => {
        const cls = l.startsWith("+") ? "diff-add" : l.startsWith("-") ? "diff-del" : l.startsWith("@@") ? "diff-hunk" : "";
        return (
          <div key={i} className={cls}>
            {l || " "}
          </div>
        );
      })}
    </div>
  );
}

function summarizeArgs(name: string, args?: Record<string, unknown>): string {
  if (!args || Object.keys(args).length === 0) return "";
  const pick =
    name === "run_shell"
      ? args.command
      : name === "run_code"
        ? args.code
        : args.path ?? args.query ?? args.pattern;
  let s: string;
  if (pick !== undefined) {
    s = String(pick);
  } else {
    const [k, v] = Object.entries(args)[0];
    s = `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`;
  }
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > 48 ? one.slice(0, 48) + "…" : one;
}

function ToolRow({ m }: { m: Extract<ChatMessage, { role: "tool" }> }) {
  const status =
    m.status === "running"
      ? { icon: <span className="thinking-entry-dot running" style={{ display: "inline-block", marginTop: 0 }} />, color: "#5b5bd6" }
      : m.status === "done"
        ? { icon: <CheckOutlined />, color: "#8b8da0" }
        : m.status === "error"
          ? { icon: <CloseOutlined />, color: "#dc2626" }
          : { icon: <CloseOutlined />, color: "#5b5bd6" };
  const summary = summarizeArgs(m.name, m.args);
  return (
    <div style={{ marginBottom: 4, opacity: m.status === "done" ? 0.85 : 1 }}>
      <Collapse
        ghost
        size="small"
        defaultActiveKey={[]}
        items={[
          {
            key: m.id,
            label: (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8, width: "100%", minWidth: 0 }}>
                <span style={{ color: status.color, fontSize: 12, flexShrink: 0 }}>{status.icon}</span>
                <span
                  style={{
                    fontFamily: "SF Mono, Menlo, Consolas, monospace",
                    fontSize: 12,
                    color: "#5f6170",
                    fontWeight: 500,
                    flexShrink: 0,
                  }}
                >
                  {m.name}
                </span>
                {summary && (
                  <span
                    style={{
                      flex: 1,
                      minWidth: 0,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      fontSize: 12,
                      color: "#8b8da0",
                    }}
                  >
                    {summary}
                  </span>
                )}
                {m.status === "rejected" && (
                  <Tag color="warning" style={{ margin: 0, flexShrink: 0 }}>
                    已拒绝
                  </Tag>
                )}
              </span>
            ),
            children: (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingLeft: 2 }}>
                {m.args && Object.keys(m.args).length > 0 && (
                  <pre
                    style={{
                      margin: 0,
                      fontSize: 12,
                      color: "#5f6170",
                      whiteSpace: "pre-wrap",
                      background: "#f7f7fb",
                      border: "1px solid #e4e5ee",
                      borderRadius: 8,
                      padding: "8px 10px",
                    }}
                  >
                    {JSON.stringify(m.args, null, 2)}
                  </pre>
                )}
                {m.status === "done" && m.result !== undefined && (
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      fontSize: 12,
                      margin: 0,
                      color: "#1c1d26",
                    }}
                  >
                    {m.result}
                  </pre>
                )}
                {m.diff && <Diff diff={m.diff} />}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

function ApprovalCard({
  m,
  onRespond,
}: {
  m: Extract<ChatMessage, { role: "approval" }>;
  onRespond: (id: string, decision: "once" | "always" | "reject") => void;
}) {
  const decided = m.status !== "pending";
  const isShell = m.tool === "run_shell";
  const command = isShell ? String(m.args.command ?? "") : "";

  return (
    <div
      style={{
        background: "#f6f6fc",
        border: "1px solid #dfe0f2",
        borderLeft: "3px solid #5b5bd6",
        borderRadius: 12,
        padding: "12px 14px",
        marginBottom: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <WarningOutlined style={{ color: "#5b5bd6" }} />
        <Typography.Text strong style={{ fontSize: 13 }}>
          {m.tool}
        </Typography.Text>
        {decided && (
          <Tag color={m.status === "rejected" ? "warning" : "success"} style={{ marginLeft: 4 }}>
            {m.status === "rejected" ? "已拒绝" : "已允许"}
          </Tag>
        )}
      </div>
      {m.message && (
        <Typography.Paragraph type="secondary" style={{ fontSize: 13, margin: "8px 0 0" }}>
          {m.message}
        </Typography.Paragraph>
      )}
      <pre
        style={{
          margin: "10px 0 0",
          fontSize: 12,
          color: "#1c1d26",
          whiteSpace: "pre-wrap",
          background: "#ffffff",
          border: "1px solid #e4e5ee",
          borderRadius: 8,
          padding: "8px 10px",
        }}
      >
        {isShell ? command : JSON.stringify(m.args, null, 2)}
      </pre>
      {!decided && (
        <Space style={{ marginTop: 12, justifyContent: "flex-end", width: "100%" }}>
          <Button size="small" danger onClick={() => onRespond(m.id, "reject")}>
            拒绝
          </Button>
          <Button size="small" onClick={() => onRespond(m.id, "once")}>
            允许一次
          </Button>
          <Button size="small" type="primary" onClick={() => onRespond(m.id, "always")}>
            总是允许
          </Button>
        </Space>
      )}
    </div>
  );
}

function formatAnswer(a: string): string {
  try {
    const p = JSON.parse(a);
    if (Array.isArray(p)) return p.join("、");
  } catch {
    // ignore
  }
  return a;
}

function AskUserCard({
  m,
  onAnswer,
}: {
  m: Extract<ChatMessage, { role: "ask_user" }>;
  onAnswer: (id: string, answer: string) => void;
}) {
  const [value, setValue] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const pending = m.status === "pending";
  const multi = m.multi ?? false;
  const options = (m.options ?? []).slice().sort(
    (a, b) => Number(b.recommended ?? false) - Number(a.recommended ?? false),
  );

  const submitText = () => {
    const t = value.trim();
    if (!t) return;
    onAnswer(m.id, t);
    setValue("");
  };

  const pickOne = (label: string) => onAnswer(m.id, label);

  const toggleMulti = (label: string) =>
    setSelected((prev) =>
      prev.includes(label) ? prev.filter((x) => x !== label) : [...prev, label],
    );

  const submitMulti = () => {
    if (selected.length === 0) return;
    onAnswer(m.id, JSON.stringify(selected));
    setSelected([]);
  };

  return (
    <div
      style={{
        background: "#f6f6fc",
        border: "1px solid #dfe0f2",
        borderLeft: "3px solid #5b5bd6",
        borderRadius: 12,
        padding: "12px 14px",
        marginBottom: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <QuestionCircleOutlined style={{ color: "#5b5bd6", marginTop: 2, flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, color: "#1c1d26", whiteSpace: "pre-wrap" }}>{m.question}</div>
          {pending && options.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 10 }}>
              {options.map((o) => {
                const active = multi && selected.includes(o.label);
                const isRec = !!o.recommended;
                return (
                  <div
                    key={o.label}
                    onClick={() => (multi ? toggleMulti(o.label) : pickOne(o.label))}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "8px 10px",
                      borderRadius: 8,
                      cursor: "pointer",
                      border: `1px solid ${active || isRec ? "#5b5bd6" : "#e4e5ee"}`,
                      background: active ? "#eef0fe" : "#ffffff",
                      transition: "border-color .15s",
                    }}
                  >
                    {multi && (
                      <span
                        style={{
                          color: active ? "#5b5bd6" : "#b9bac9",
                          flexShrink: 0,
                          fontSize: 12,
                        }}
                      >
                        {active ? "●" : "○"}
                      </span>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: isRec ? 600 : 400,
                          color: "#1c1d26",
                        }}
                      >
                        {o.label}
                      </div>
                      {o.description && (
                        <div style={{ fontSize: 12, color: "#8b8da0", marginTop: 2 }}>
                          {o.description}
                        </div>
                      )}
                    </div>
                    {isRec && (
                      <Tag color="purple" style={{ margin: 0, flexShrink: 0 }}>
                        推荐
                      </Tag>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {pending && multi && selected.length > 0 && (
            <Button size="small" type="primary" style={{ marginTop: 10 }} onClick={submitMulti}>
              提交所选（{selected.length}）
            </Button>
          )}
          {pending ? (
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
              <Input
                size="small"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onPressEnter={submitText}
                placeholder={options.length > 0 ? "或输入自定义回答…" : "输入回答…"}
                autoFocus={options.length === 0}
              />
              <Button type="primary" size="small" onClick={submitText}>
                发送
              </Button>
            </div>
          ) : (
            m.answer !== undefined && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#8b8da0", whiteSpace: "pre-wrap" }}>
                你：{formatAnswer(m.answer)}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

function SafetyCard({
  m,
  onDecision,
}: {
  m: Extract<ChatMessage, { role: "safety" }>;
  onDecision: (id: string, decision: "continue" | "abort") => void;
}) {
  const pending = m.status === "pending";
  return (
    <div
      style={{
        background: "#fdf7f1",
        border: "1px solid #f2e2cd",
        borderLeft: "3px solid #d97706",
        borderRadius: 12,
        padding: "12px 14px",
        marginBottom: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <WarningOutlined style={{ color: "#d97706", marginTop: 2, flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#7c4a12" }}>检测到安全风险</div>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, color: "#8a6a3f" }}>
            {m.reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          {pending ? (
            <Space style={{ marginTop: 12 }}>
              <Button size="small" danger onClick={() => onDecision(m.id, "abort")}>
                取消执行
              </Button>
              <Button size="small" type="primary" onClick={() => onDecision(m.id, "continue")}>
                仍然继续
              </Button>
            </Space>
          ) : (
            <Tag style={{ marginTop: 8 }} color={m.status === "allowed" ? "success" : "warning"}>
              {m.status === "allowed" ? "已允许" : "已阻止"}
            </Tag>
          )}
        </div>
      </div>
    </div>
  );
}

function b64ToText(b64: string): string {
  try {
    const bin = atob(b64);
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return "";
  }
}

function AttachmentList({ attachments }: { attachments?: Attachment[] }) {
  if (!attachments || attachments.length === 0) return null;
  return (
    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
      {attachments.map((a, i) => {
        const isText = a.media_type.startsWith("text/");
        const isImage = a.media_type.startsWith("image/");
        const isPdf = a.media_type === "application/pdf";
        return (
          <Collapse
            ghost
            size="small"
            key={`${a.name}_${i}`}
            items={[
              {
                key: `${i}`,
                label: (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#5f6170", fontSize: 12 }}>
                    <PaperClipOutlined style={{ fontSize: 12 }} />
                    {a.name}
                  </span>
                ),
                children: (() => {
                  if (isText) {
                    return (
                      <pre
                        style={{
                          margin: 0,
                          fontSize: 12,
                          color: "#1c1d26",
                          whiteSpace: "pre-wrap",
                          background: "#f7f7fb",
                          border: "1px solid #e4e5ee",
                          borderRadius: 8,
                          padding: "8px 10px",
                          maxHeight: 320,
                          overflow: "auto",
                        }}
                      >
                        {b64ToText(a.data_b64)}
                      </pre>
                    );
                  }
                  if (isImage) {
                    return (
                      <img
                        src={`data:${a.media_type};base64,${a.data_b64}`}
                        alt={a.name}
                        style={{ maxWidth: "100%", borderRadius: 8 }}
                      />
                    );
                  }
                  if (isPdf) {
                    return (
                      <span style={{ fontSize: 12, color: "#8b8da0" }}>
                        PDF 附件（已发送给模型，此处不预览）
                      </span>
                    );
                  }
                  return (
                    <span style={{ fontSize: 12, color: "#8b8da0" }}>
                      {a.media_type} 附件
                    </span>
                  );
                })(),
              },
            ]}
          />
        );
      })}
    </div>
  );
}

function ContentFlag({ m }: { m: Extract<ChatMessage, { role: "content_flag" }> }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12,
        color: "#a15c00",
        marginBottom: 12,
      }}
    >
      <WarningOutlined style={{ color: "#d97706" }} />
      <span>{m.message}</span>
    </div>
  );
}

function ThinkingRow({ entries, active }: { entries: ThinkingEntry[]; active: boolean }) {
  if (entries.length === 0 && active) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, color: "#b9bac9", fontSize: 12 }}>
        <span className="thinking-mini-dots">
          <i />
          <i />
          <i />
        </span>
        <span>思考中…</span>
      </div>
    );
  }
  if (entries.length === 0) return null;
  const latestProgress = [...entries]
    .reverse()
    .find((e) => e.kind === "progress" && e.status === "running");
  const headerText = active ? (latestProgress?.title ?? "思考中…") : "思考";
  const timelineEntries = entries.filter((e) => e.kind !== "progress");
  return (
    <div style={{ marginBottom: 16 }}>
      <Collapse
        ghost
        size="small"
        defaultActiveKey={[]}
        items={[
          {
            key: "thinking",
            label: (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#8b8da0", fontSize: 12 }}>
                <BulbOutlined style={{ fontSize: 12 }} />
                {active && (
                  <span className="thinking-mini-dots">
                    <i />
                    <i />
                    <i />
                  </span>
                )}
                <span>{headerText}</span>
              </span>
            ),
            children: timelineEntries.length === 0 ? (
              <span style={{ fontSize: 12, color: "#8b8da0" }}>暂无更多细节</span>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  paddingTop: 2,
                  paddingLeft: 12,
                  borderLeft: "2px solid #e4e5ee",
                }}
              >
                {timelineEntries.map((e) => (
                  <div key={e.id} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                    <span className={`thinking-entry-dot ${e.status ?? ""}`} />
                    <div style={{ minWidth: 0 }}>
                      <span style={{ fontSize: 13, fontWeight: 450, color: "#5f6170" }}>
                        {e.title}
                      </span>
                      {e.detail && (
                        <div style={{ fontSize: 12, color: "#8b8da0", marginTop: 2 }}>{e.detail}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}

export default function MessageList({
  messages,
  thinking = [],
  thinkingActive = false,
  onRespond,
  onAnswer,
  onSafety,
}: {
  messages: ChatMessage[];
  thinking?: ThinkingEntry[];
  thinkingActive?: boolean;
  onRespond?: (id: string, decision: "once" | "always" | "reject") => void;
  onAnswer?: (id: string, answer: string) => void;
  onSafety?: (id: string, decision: "continue" | "abort") => void;
}) {
  if (messages.length === 0) {
    return (
      <div style={{ padding: "48px 8px", textAlign: "center" }}>
        <img src={logo} className="app-logo-img app-logo-img-lg" alt="myopencode" style={{ margin: "0 auto 20px" }} />
        <div style={{ fontSize: 26, color: "#1c1d26", fontWeight: 600 }}>
          有什么可以帮你？
        </div>
        <div style={{ marginTop: 10, fontSize: 14, color: "#8b8da0" }}>
          让 Agent 读写文件、搜索代码、执行命令，帮你完成编程任务
        </div>
      </div>
    );
  }

  const showThinking = thinking.length > 0 || thinkingActive;
  let lastUserIndex = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      lastUserIndex = i;
      break;
    }
  }

  const rows: ReactNode[] = [];
  messages.forEach((m, i) => {
    if (m.role === "tool") {
      rows.push(<ToolRow key={m.id} m={m} />);
      return;
    }
    if (m.role === "approval") {
      rows.push(<ApprovalCard key={m.id} m={m} onRespond={onRespond ?? (() => {})} />);
      return;
    }
    if (m.role === "ask_user") {
      rows.push(<AskUserCard key={m.id} m={m} onAnswer={onAnswer ?? (() => {})} />);
      return;
    }
    if (m.role === "safety") {
      rows.push(<SafetyCard key={m.id} m={m} onDecision={onSafety ?? (() => {})} />);
      return;
    }
    if (m.role === "content_flag") {
      rows.push(<ContentFlag key={m.id} m={m} />);
      return;
    }
    const isUser = m.role === "user";
    rows.push(
      <div
        key={m.id}
        style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 22 }}
      >
        <div
          style={{
            flexShrink: 0,
            width: 30,
            height: 30,
            borderRadius: "50%",
            background: isUser ? "#e4e5ee" : "linear-gradient(135deg, #6d6ae0, #4f46e5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: isUser ? "#5f6170" : "#fff",
          }}
        >
          {isUser ? <UserOutlined /> : <RobotOutlined />}
        </div>
        <div style={{ flex: 1, minWidth: 0, paddingTop: 3 }}>
          <div
            className={isUser ? undefined : "markdown-body"}
            style={{ color: "#1c1d26", whiteSpace: isUser ? "pre-wrap" : undefined }}
          >
            {isUser ? (
              <Typography.Text style={{ fontSize: 15 }}>{m.content}</Typography.Text>
            ) : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
            )}
            {m.streaming && <LoadingOutlined style={{ marginLeft: 6, color: "#5b5bd6" }} />}
          </div>
          <AttachmentList attachments={m.attachments} />
        </div>
      </div>,
    );
    if (i === lastUserIndex && showThinking) {
      rows.push(<ThinkingRow key="thinking" entries={thinking} active={thinkingActive} />);
    }
  });

  return <div>{rows}</div>;
}