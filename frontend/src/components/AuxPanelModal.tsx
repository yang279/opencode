import { Modal, Tabs } from "antd";
import SkillsPanel from "./SkillsPanel";
import ToolsPanel from "./ToolsPanel";
import UsagePanel from "./UsagePanel";
import DiagnosticsPanel from "./DiagnosticsPanel";
import KnowledgeBasePanel from "./KnowledgeBasePanel";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function AuxPanelModal({ open, onClose }: Props) {
  return (
    <Modal
      open={open}
      title="工具与信息"
      footer={null}
      onCancel={onClose}
      width={620}
      centered
      styles={{
        body: { maxHeight: "calc(100vh - 200px)", overflowY: "auto", scrollbarGutter: "stable" },
      }}
    >
      <Tabs
        defaultActiveKey="usage"
        items={[
          { key: "skills", label: "Skills", children: <SkillsPanel /> },
          { key: "tools", label: "工具", children: <ToolsPanel /> },
          { key: "knowledge", label: "知识库", children: <KnowledgeBasePanel /> },
          { key: "usage", label: "用量预算", children: <UsagePanel /> },
          { key: "diagnostics", label: "诊断", children: <DiagnosticsPanel /> },
        ]}
      />
    </Modal>
  );
}