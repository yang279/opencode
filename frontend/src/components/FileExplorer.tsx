import { useEffect, useState } from "react";
import { Tree, Typography, Spin } from "antd";
import type { DataNode } from "antd/es/tree";
import { FileOutlined } from "@ant-design/icons";
import { api, type TreeEntry } from "../lib/api";

function buildTree(entries: TreeEntry[]): DataNode[] {
  const nodes = new Map<string, DataNode>();
  const roots: DataNode[] = [];
  for (const e of entries) {
    const key = e.path;
    const parts = e.path.split("/");
    const node: DataNode = {
      key,
      title: parts[parts.length - 1] || key,
      isLeaf: e.type === "file",
      children: e.type === "file" ? undefined : [],
      icon: e.type === "file" ? <FileOutlined /> : null,
    };
    nodes.set(key, node);
    const parent = parts.slice(0, -1).join("/");
    if (!parent) {
      roots.push(node);
    } else if (nodes.has(parent)) {
      (nodes.get(parent)!.children as DataNode[]).push(node);
    }
  }
  return roots;
}

export default function FileExplorer() {
  const [entries, setEntries] = useState<TreeEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .workspaceTree()
      .then((r) => setEntries(r.entries))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin style={{ padding: 16 }} />;

  return (
    <div style={{ padding: 14, height: "100%", overflow: "auto" }}>
      <Typography.Text style={{ fontSize: 12, color: "#5f6170" }}>
        工作区文件
      </Typography.Text>
      <Tree
        showLine
        defaultExpandAll={false}
        treeData={buildTree(entries)}
        blockNode
        style={{ background: "transparent", marginTop: 8 }}
        aria-label="工作区文件"
      />
    </div>
  );
}