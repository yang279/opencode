import { useEffect, useState } from "react";
import { Button, Spin, Space, Typography, Tag, Table } from "antd";
import { ReloadOutlined, DownloadOutlined } from "@ant-design/icons";
import { api, type Diagnostics, type TraceSpan } from "../lib/api";

function badge(v: boolean) {
  return <Tag color={v ? "success" : "default"}>{v ? "开" : "关"}</Tag>;
}

function fmtBytes(n: number | null) {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export default function DiagnosticsPanel() {
  const [data, setData] = useState<Diagnostics | null>(null);
  const [spans, setSpans] = useState<TraceSpan[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([api.getDiagnostics(), api.getTraces()])
      .then(([d, t]) => {
        setData(d);
        setSpans(t.spans);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const onExport = async () => {
    setExporting(true);
    try {
      const url = await api.diagnosticsExportUrl();
      window.open(url, "_blank");
    } finally {
      setExporting(false);
    }
  };

  if (loading) return <Spin style={{ padding: 16 }} />;
  if (!data) return <Typography.Text>无法加载诊断信息</Typography.Text>;

  return (
    <div style={{ padding: "4px 2px" }}>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 8 }}>
        <Typography.Text strong style={{ fontSize: 12 }}>
          运行状态 <Tag color="success">{data.status}</Tag>
        </Typography.Text>
        <Space size={4}>
          <Button size="small" type="text" icon={<ReloadOutlined />} onClick={load} />
          <Button size="small" icon={<DownloadOutlined />} loading={exporting} onClick={onExport}>
            导出
          </Button>
        </Space>
      </Space>

      <Typography.Text style={{ fontSize: 12, color: "#6e6a63" }}>模型</Typography.Text>
      <div style={{ fontSize: 12, marginBottom: 4 }}>
        {data.provider.name}
        {data.provider.model ? ` · ${data.provider.model}` : ""}{" "}
        <Tag color={data.provider.configured ? "success" : "error"}>
          {data.provider.configured ? "已配置" : "未配置 Key"}
        </Tag>
      </div>

      <Typography.Text style={{ fontSize: 12, color: "#6e6a63" }}>沙箱</Typography.Text>
      <div style={{ fontSize: 12, marginBottom: 4 }}>
        {data.sandbox.enabled ? data.sandbox.backend : "已禁用"}{" "}
        <Tag color={data.sandbox.backend === "pathguard" ? "warning" : "default"}>
          {data.sandbox.backend === "pathguard" ? "无 OS 隔离" : "隔离中"}
        </Tag>
      </div>

      <Typography.Text style={{ fontSize: 12, color: "#6e6a63" }}>功能开关</Typography.Text>
      <div style={{ marginBottom: 4 }}>
        {Object.entries(data.features).map(([k, v]) => (
          <span key={k} style={{ marginRight: 4, fontSize: 11 }}>
            {k} {badge(v)}
          </span>
        ))}
      </div>

      <Typography.Text style={{ fontSize: 12, color: "#6e6a63" }}>内存 / 磁盘</Typography.Text>
      <div style={{ fontSize: 12, marginBottom: 4 }}>
        峰值 RSS {fmtBytes(data.process.maxrss_bytes)} · 日志 {fmtBytes(data.disk.logs)} · 审计{" "}
        {fmtBytes(data.disk.audit)}
      </div>

      {spans.length > 0 && (
        <>
          <Typography.Text style={{ fontSize: 12, color: "#6e6a63" }}>最近 Span</Typography.Text>
          <Table<TraceSpan>
            size="small"
            rowKey="span_id"
            pagination={false}
            dataSource={spans.slice(0, 20)}
            columns={[
              { title: "名称", dataIndex: "name", key: "name" },
              {
                title: "耗时",
                dataIndex: "duration_ms",
                key: "duration_ms",
                render: (v: number) => `${v}ms`,
              },
            ]}
          />
        </>
      )}
    </div>
  );
}