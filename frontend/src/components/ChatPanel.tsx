import { useEffect, useRef, useState } from "react";
import { Button, Input } from "antd";
import { SendOutlined, StopOutlined, PlusOutlined, CloseOutlined } from "@ant-design/icons";
import MessageList from "./MessageList";
import type { ChatMessage, ThinkingEntry } from "../types/events";

interface Props {
  messages: ChatMessage[];
  thinking: ThinkingEntry[];
  running: boolean;
  onSend: (content: string) => boolean;
  onCancel: () => void;
  onRespond: (id: string, decision: "once" | "always" | "reject") => void;
  onAnswer: (id: string, answer: string) => void;
  onSafety: (id: string, decision: "continue" | "abort") => void;
}

interface Attachment {
  id: string;
  name: string;
  content: string;
}

let attSeq = 0;
const genAttId = () => `a${Date.now()}_${attSeq++}`;

function buildMessage(text: string, attachments: Attachment[]): string {
  if (attachments.length === 0) return text;
  const parts = attachments
    .map((a) => `### 文件: ${a.name}\n\`\`\`\n${a.content}\n\`\`\``)
    .join("\n\n");
  if (text) {
    return `以下是用户附带的文件内容：\n\n${parts}\n\n用户要求：${text}`;
  }
  return `以下是用户附带的文件内容：\n\n${parts}\n\n请分析这些文件。`;
}

export default function ChatPanel({ messages, thinking, running, onSend, onCancel, onRespond, onAnswer, onSafety }: Props) {
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = dist < 80;
    atBottomRef.current = atBottom;
    setShowJump(!atBottom);
  };

  const jumpToBottom = () => {
    atBottomRef.current = true;
    setShowJump(false);
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    const last = messages[messages.length - 1];
    if (atBottomRef.current || last?.role === "user" || last?.role === "approval") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const items = await Promise.all(
      Array.from(files).map(async (f) => ({
        id: genAttId(),
        name: f.name,
        content: await f.text(),
      })),
    );
    setAttachments((prev) => [...prev, ...items]);
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const hasContent = !!input.trim() || attachments.length > 0;

  const submit = () => {
    if (!hasContent) return;
    const accepted = onSend(buildMessage(input.trim(), attachments));
    if (accepted) {
      setInput("");
      setAttachments([]);
    }
  };
  const hasStreaming = messages.some((m) => m.role === "assistant" && m.streaming);
  const last = messages[messages.length - 1];
  const activeTool = last?.role === "tool" && last.status === "running";
  const hasPendingApproval = messages.some((m) => m.role === "approval" && m.status === "pending");
  const hasPendingQuestion = messages.some((m) => m.role === "ask_user" && m.status === "pending");
  const hasPendingSafety = messages.some((m) => m.role === "safety" && m.status === "pending");
  const thinkingActive =
    running && !hasStreaming && !activeTool && !hasPendingApproval && !hasPendingQuestion && !hasPendingSafety;

  return (
    <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
      <div style={{ flex: 1, minHeight: 0, position: "relative", display: "flex", flexDirection: "column" }}>
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          style={{ flex: 1, minHeight: 0, overflow: "auto", scrollbarGutter: "stable" }}
        >
          <div style={{ maxWidth: 780, margin: "0 auto", padding: "20px 24px 8px" }}>
            <MessageList
              messages={messages}
              thinking={thinking}
              thinkingActive={thinkingActive}
              onRespond={onRespond}
              onAnswer={onAnswer}
              onSafety={onSafety}
            />
            <div ref={bottomRef} />
          </div>
        </div>
        {showJump && (
          <button
            onClick={jumpToBottom}
            className="jump-to-bottom"
            title="回到底部"
          >
            ↓ 回到底部
          </button>
        )}
      </div>

      <div style={{ flexShrink: 0, padding: "12px 24px 20px" }}>
        <div style={{ maxWidth: 780, margin: "0 auto" }}>
          {attachments.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
              {attachments.map((a) => (
                <span
                  key={a.id}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    background: "#f0eee6",
                    border: "1px solid #e8e6dc",
                    borderRadius: 8,
                    padding: "3px 8px",
                    fontSize: 12,
                    color: "#4a463f",
                    maxWidth: 260,
                  }}
                >
                  <span
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {a.name}
                  </span>
                  <CloseOutlined
                    onClick={() => removeAttachment(a.id)}
                    style={{ fontSize: 10, color: "#8a857b", cursor: "pointer" }}
                  />
                </span>
              ))}
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            multiple
            style={{ display: "none" }}
            onChange={(e) => {
              handleFiles(e.target.files);
              e.target.value = "";
            }}
          />

          <div
            style={{
              display: "flex",
              alignItems: "flex-end",
              gap: 8,
              background: "#ffffff",
              border: "1px solid #e8e6dc",
              borderRadius: 18,
              padding: "8px 8px 8px 12px",
              boxShadow: "0 2px 16px rgba(31, 30, 29, 0.06)",
            }}
          >
            <Button
              shape="circle"
              icon={<PlusOutlined />}
              onClick={() => fileInputRef.current?.click()}
              title="添加文件"
              style={{ flexShrink: 0, border: "none", background: "#f0eee6", color: "#4a463f" }}
            />
            <Input.TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="描述你想让 Agent 做的事…"
              autoSize={{ minRows: 1, maxRows: 6 }}
              style={{ flex: 1, border: "none", boxShadow: "none", background: "transparent", resize: "none", padding: "6px 0" }}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <Button
              type="primary"
              shape="circle"
              size="large"
              icon={running ? <StopOutlined /> : <SendOutlined />}
              onClick={() => (running ? onCancel() : submit())}
              disabled={!running && !hasContent}
              style={{ flexShrink: 0 }}
            />
          </div>
          <div style={{ textAlign: "center", fontSize: 12, color: "#8a857b", marginTop: 10 }}>
            Agent 可以读写文件、执行命令，操作前会请求确认
          </div>
        </div>
      </div>
    </div>
  );
}