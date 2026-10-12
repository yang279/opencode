import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import MessageList from "../MessageList";
import type { ChatMessage } from "../../types/events";

describe("MessageList", () => {
  it("renders welcome when no messages", () => {
    render(<MessageList messages={[]} />);
    expect(screen.getByText("有什么可以帮你？")).toBeInTheDocument();
  });

  it("renders user message content", () => {
    const messages: ChatMessage[] = [{ id: "m1", role: "user", content: "帮我写个函数" }];
    render(<MessageList messages={messages} />);
    expect(screen.getByText("帮我写个函数")).toBeInTheDocument();
  });

  it("renders running tool name with pulsing dot", () => {
    const messages: ChatMessage[] = [
      { id: "t1", role: "tool", name: "run_shell", args: { command: "ls" }, status: "running" },
    ];
    const { container } = render(<MessageList messages={messages} />);
    expect(screen.getByText("run_shell")).toBeInTheDocument();
    expect(container.querySelector(".thinking-entry-dot.running")).toBeInTheDocument();
  });

  it("renders pending ask_user with options", () => {
    const messages: ChatMessage[] = [
      {
        id: "q1",
        role: "ask_user",
        question: "选哪个框架？",
        options: [
          { label: "React", recommended: true },
          { label: "Vue" },
        ],
        status: "pending",
      },
    ];
    render(<MessageList messages={messages} />);
    expect(screen.getByText("选哪个框架？")).toBeInTheDocument();
    expect(screen.getByText("React")).toBeInTheDocument();
    expect(screen.getByText("Vue")).toBeInTheDocument();
  });

  it("renders pending approval with action buttons", () => {
    const messages: ChatMessage[] = [
      {
        id: "a1",
        role: "approval",
        tool: "run_shell",
        args: { command: "rm -rf" },
        message: "需要确认",
        status: "pending",
      },
    ];
    render(<MessageList messages={messages} />);
    expect(screen.getByText("run_shell")).toBeInTheDocument();
    expect(screen.getByText("允许一次")).toBeInTheDocument();
    expect(screen.getByText(/拒\s*绝/)).toBeInTheDocument();
  });

  it("renders pending safety warning", () => {
    const messages: ChatMessage[] = [
      { id: "s1", role: "safety", reasons: ["危险命令"], severity: "high", status: "pending" },
    ];
    render(<MessageList messages={messages} />);
    expect(screen.getByText("检测到安全风险")).toBeInTheDocument();
  });
});