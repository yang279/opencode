import { useEffect, useRef } from "react";
import { Button, Typography } from "antd";
import { CloseOutlined } from "@ant-design/icons";
import type { TerminalLine } from "../hooks/useAgent";

const COLORS: Record<TerminalLine["kind"], string> = {
  cmd: "#b8562f",
  out: "#1f1e1d",
  err: "#c62828",
  info: "#2e7d32",
};

export default function TerminalPanel({
  lines,
  onClose,
}: {
  lines: TerminalLine[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [lines]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#f5f3ec" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 8px 6px 14px",
          borderBottom: "1px solid #e8e6dc",
        }}
      >
        <Typography.Text style={{ fontSize: 12, color: "#8a857b" }}>
          终端 / 工具输出
        </Typography.Text>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Typography.Text style={{ fontSize: 11, color: "#b0aca1" }}>F12 收起</Typography.Text>
          <Button size="small" type="text" icon={<CloseOutlined />} onClick={onClose} />
        </span>
      </div>
      <div
        ref={ref}
        style={{
          flex: 1,
          overflow: "auto",
          padding: "8px 14px",
        }}
      >
      {lines.map((l) => (
        <div
          key={l.id}
          style={{
            fontFamily: "SF Mono, Menlo, Consolas, monospace",
            fontSize: 12,
            color: COLORS[l.kind],
            whiteSpace: "pre-wrap",
            marginTop: 2,
          }}
        >
          {l.text}
        </div>
      ))}
      </div>
    </div>
  );
}