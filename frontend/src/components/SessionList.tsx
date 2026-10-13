import { Button, Empty } from "antd";
import { PlusOutlined, MessageOutlined, DeleteOutlined } from "@ant-design/icons";
import type { SessionMeta } from "../lib/api";

interface Props {
  sessions: SessionMeta[];
  activeSessionId: string | null;
  onNew: () => void;
  onSwitch: (id: string) => void;
  onDelete: (id: string) => void;
}

export default function SessionList({
  sessions,
  activeSessionId,
  onNew,
  onSwitch,
  onDelete,
}: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "10px 12px 8px" }}>
        <Button block icon={<PlusOutlined />} onClick={onNew}>
          新建会话
        </Button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: "auto", scrollbarGutter: "stable", padding: "0 6px 8px" }}>
        {sessions.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<span style={{ fontSize: 12, color: "#8b8da0" }}>暂无会话</span>}
          />
        ) : (
          sessions.map((s) => {
            const active = s.id === activeSessionId;
            return (
              <div
                key={s.id}
                onClick={() => onSwitch(s.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 10px",
                  borderRadius: 8,
                  cursor: "pointer",
                  marginBottom: 2,
                  background: active ? "#eef0fe" : "transparent",
                  color: active ? "#1c1d26" : "#5f6170",
                }}
              >
                <MessageOutlined style={{ fontSize: 12, color: active ? "#5b5bd6" : "#8b8da0", flexShrink: 0 }} />
                <span
                  style={{
                    flex: 1,
                    fontSize: 13,
                    fontWeight: active ? 600 : 400,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {s.title}
                </span>
                <DeleteOutlined
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(s.id);
                  }}
                  style={{ fontSize: 12, color: "#b9bac9", flexShrink: 0 }}
                />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}