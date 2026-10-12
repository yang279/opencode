import { useEffect, useState } from "react";
import { Layout, Space, Typography, Tag, Button, Alert } from "antd";
import { ApiOutlined, SettingOutlined, ToolOutlined } from "@ant-design/icons";
import { api } from "./lib/api";
import { useAgent } from "./hooks/useAgent";
import ChatPanel from "./components/ChatPanel";
import SessionList from "./components/SessionList";
import TerminalPanel from "./components/TerminalPanel";
import ConfigModal from "./components/ConfigModal";
import AuxPanelModal from "./components/AuxPanelModal";

const { Header, Sider, Content } = Layout;

export default function App() {
  const agent = useAgent();
  const [provider, setProvider] = useState<string>("…");
  const [version, setVersion] = useState<string>("");
  const [configOpen, setConfigOpen] = useState(false);
  const [auxOpen, setAuxOpen] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [healthTick, setHealthTick] = useState(0);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "F12") {
        e.preventDefault();
        setTerminalOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setProvider(h.provider);
        setVersion(h.version);
      })
      .catch(() => {});
  }, [agent.connected, healthTick]);

  return (
    <Layout style={{ height: "100vh", background: "#faf9f5" }}>
      <Header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 18px",
          height: 52,
          lineHeight: "52px",
          background: "#faf9f5",
          borderBottom: "1px solid #eeece3",
        }}
      >
        <Space size={10} align="center">
          <span className="claude-logo">*</span>
          <Typography.Text strong className="serif" style={{ fontSize: 17, color: "#1f1e1d" }}>
            myopencode
          </Typography.Text>
          <Tag
            color={agent.connected ? "success" : "error"}
            style={{ marginLeft: 4 }}
          >
            {agent.connected ? "已连接" : "未连接"}
          </Tag>
          <Tag icon={<ApiOutlined />} style={{ background: "#f0eee6", border: "1px solid #e8e6dc", color: "#6e6a63" }}>
            {provider}
          </Tag>
          {version && <Tag style={{ background: "#f0eee6", border: "1px solid #e8e6dc", color: "#6e6a63" }}>v{version}</Tag>}
        </Space>
        {agent.resumable && !agent.running && (
          <Button size="small" onClick={agent.resume}>
            继续上次任务
          </Button>
        )}
      </Header>

      <Layout style={{ background: "#faf9f5" }}>
        <Sider
          width={260}
          style={{ background: "#f5f3ec", borderRight: "1px solid #e8e6dc" }}
        >
          <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
            <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
              <SessionList
                sessions={agent.sessions}
                activeSessionId={agent.activeSessionId}
                onNew={() => agent.newSession()}
                onSwitch={agent.switchSession}
                onDelete={agent.deleteSession}
              />
            </div>
            <div style={{ padding: 12, borderTop: "1px solid #e8e6dc", display: "flex", flexDirection: "column", gap: 8 }}>
              <Button block icon={<ToolOutlined />} onClick={() => setAuxOpen(true)}>
                工具与信息
              </Button>
              <Button block icon={<SettingOutlined />} onClick={() => setConfigOpen(true)}>
                配置
              </Button>
            </div>
          </div>
        </Sider>
        <Content style={{ display: "flex", flexDirection: "column", minHeight: 0, background: "#faf9f5" }}>
          {agent.error && (
            <Alert
              type="error"
              message={agent.error}
              closable
              onClose={agent.clearError}
              style={{ margin: 8 }}
            />
          )}
          {agent.degraded && (
            <Alert
              type="warning"
              message={agent.degraded}
              closable
              onClose={agent.clearDegraded}
              style={{ margin: 8 }}
            />
          )}
          <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <ChatPanel
              messages={agent.messages}
              thinking={agent.thinking}
              running={agent.running}
              onSend={agent.sendMessage}
              onCancel={agent.cancel}
              onRespond={agent.respondApproval}
              onAnswer={agent.respondAnswer}
              onSafety={agent.respondSafety}
            />
            {terminalOpen && (
              <div style={{ height: 220, borderTop: "1px solid #e8e6dc", flexShrink: 0 }}>
                <TerminalPanel lines={agent.terminal} onClose={() => setTerminalOpen(false)} />
              </div>
            )}
          </div>
        </Content>
      </Layout>

      <AuxPanelModal open={auxOpen} onClose={() => setAuxOpen(false)} />
      <ConfigModal
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        onSaved={() => setHealthTick((t) => t + 1)}
      />
    </Layout>
  );
}