import { useEffect, useState } from "react";
import { List, Typography, Spin, Empty } from "antd";
import { CodeOutlined } from "@ant-design/icons";
import { api, type ToolMeta } from "../lib/api";

export default function ToolsPanel() {
  const [tools, setTools] = useState<ToolMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getTools()
      .then(setTools)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin style={{ padding: 16 }} />;

  if (tools.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span style={{ fontSize: 12, color: "#8b8da0" }}>
            暂无 MCP 工具
            <br />
            在 myopencode.json 里配置 mcp_servers
          </span>
        }
      />
    );
  }

  return (
    <List
      size="small"
      dataSource={tools}
      renderItem={(t) => (
        <List.Item style={{ padding: "10px 4px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <CodeOutlined style={{ color: "#8b8da0" }} />
              <Typography.Text strong style={{ fontSize: 13 }}>
                {t.name}
              </Typography.Text>
            </div>
            <Typography.Text
              style={{ fontSize: 12, color: "#8b8da0", display: "block", marginTop: 2 }}
            >
              {t.description}
            </Typography.Text>
          </div>
        </List.Item>
      )}
    />
  );
}