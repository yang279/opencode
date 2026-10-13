import { useEffect, useRef, useState } from "react";
import { Button, Input, message } from "antd";
import { SendOutlined, StopOutlined, PlusOutlined, CloseOutlined } from "@ant-design/icons";
import MessageList from "./MessageList";
import { api } from "../lib/api";
import type { Attachment, ChatMessage, ThinkingEntry } from "../types/events";

const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;

const EXT_MIME: Record<string, string> = {
  pdf: "application/pdf",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  txt: "text/plain",
  md: "text/markdown",
  json: "application/json",
  py: "text/x-python",
  js: "text/javascript",
  ts: "text/plain",
  html: "text/html",
  css: "text/css",
  yml: "text/plain",
  yaml: "text/plain",
  xml: "text/xml",
  csv: "text/csv",
  sh: "text/plain",
  rs: "text/plain",
  go: "text/plain",
  java: "text/plain",
  c: "text/plain",
  cpp: "text/plain",
  h: "text/plain",
};

function inferMime(name: string, fileType: string): string {
  if (fileType) return fileType;
  const ext = (name.split(".").pop() || "").toLowerCase();
  return EXT_MIME[ext] || "text/plain";
}

type AttachmentAction = "text" | "image" | "pdf-native" | "pdf-extract" | "block";

function attachmentAction(provider: string, mediaType: string): AttachmentAction {
  if (mediaType.startsWith("text/")) return "text";
  if (mediaType.startsWith("image/")) {
    if (provider === "anthropic" || provider === "openai") return "image";
    return "block";
  }
  if (mediaType === "application/pdf") {
    if (provider === "anthropic") return "pdf-native";
    if (provider === "openai" || provider === "ollama") return "pdf-extract";
    return "block";
  }
  return "block";
}

function arrayBufferToBase64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...Array.from(bytes.subarray(i, i + chunk)));
  }
  return btoa(binary);
}

interface AttachItem extends Attachment {
  id: string;
}

interface Props {
  messages: ChatMessage[];
  thinking: ThinkingEntry[];
  running: boolean;
  onSend: (content: string, attachments: Attachment[]) => boolean;
  onCancel: () => void;
  onRespond: (id: string, decision: "once" | "always" | "reject") => void;
  onAnswer: (id: string, answer: string) => void;
  onSafety: (id: string, decision: "continue" | "abort") => void;
  provider?: string;
}

let attSeq = 0;
const genAttId = () => `a${Date.now()}_${attSeq++}`;

export default function ChatPanel({ messages, thinking, running, onSend, onCancel, onRespond, onAnswer, onSafety, provider = "" }: Props) {
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<AttachItem[]>([]);
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
    const items: AttachItem[] = [];
    for (const f of Array.from(files)) {
      if (f.size > MAX_ATTACHMENT_BYTES) {
        message.error(`文件 ${f.name} 超过 20MB 上限`);
        continue;
      }
      const media_type = inferMime(f.name, f.type);
      const action = attachmentAction(provider, media_type);
      if (action === "block") {
        message.error(`当前模型不支持该文件类型：${f.name}（${media_type}）`);
        continue;
      }
      const data_b64 = arrayBufferToBase64(await f.arrayBuffer());
      if (action === "pdf-extract") {
        try {
          const res = await api.extractPdf(data_b64);
          if (res.error) {
            message.error(`PDF 解析失败：${res.error}`);
            continue;
          }
          const textB64 = arrayBufferToBase64(new TextEncoder().encode(res.text ?? ""));
          items.push({ id: genAttId(), name: f.name, media_type: "text/plain", data_b64: textB64 });
        } catch (e) {
          message.error(`PDF 解析失败：${String(e)}`);
        }
        continue;
      }
      items.push({ id: genAttId(), name: f.name, media_type, data_b64 });
    }
    if (items.length > 0) {
      setAttachments((prev) => [...prev, ...items]);
    }
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const hasContent = !!input.trim() || attachments.length > 0;

  const submit = () => {
    if (!hasContent) return;
    const payload: Attachment[] = attachments.map(({ name, media_type, data_b64 }) => ({
      name,
      media_type,
      data_b64,
    }));
    const accepted = onSend(input.trim(), payload);
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
                    background: "#eef0f6",
                    border: "1px solid #e4e5ee",
                    borderRadius: 8,
                    padding: "3px 8px",
                    fontSize: 12,
                    color: "#5f6170",
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
                    style={{ fontSize: 10, color: "#8b8da0", cursor: "pointer" }}
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
              border: "1px solid #d2d3e0",
              borderRadius: 18,
              padding: "8px 8px 8px 12px",
              boxShadow: "0 2px 16px rgba(28, 29, 38, 0.08)",
            }}
          >
            <Button
              shape="circle"
              icon={<PlusOutlined />}
              onClick={() => fileInputRef.current?.click()}
              title="添加文件"
              style={{ flexShrink: 0, border: "none", background: "#eef0f6", color: "#5f6170" }}
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
          <div style={{ textAlign: "center", fontSize: 12, color: "#8b8da0", marginTop: 10 }}>
            Agent 可以读写文件、执行命令，操作前会请求确认
          </div>
        </div>
      </div>
    </div>
  );
}