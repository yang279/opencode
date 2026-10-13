import { useEffect, useState } from "react";
import { Button, Spin, Typography, Empty } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { api, type UsageSummary } from "../lib/api";

const C = {
  bg: "#f7f7fb",
  card: "#f6f6fc",
  border: "#e4e5ee",
  text: "#1c1d26",
  sub: "#5f6170",
  faint: "#8b8da0",
  orange: "#5b5bd6",
  deepOrange: "#4f46e5",
  red: "#dc2626",
  green: "#16a34a",
  track: "#e4e5ee",
};

function fmt(n: number) {
  return `$${n.toFixed(4)}`;
}

function pct(spent: number, budget: number | null) {
  if (budget == null || budget <= 0) return null;
  return Math.min(100, Math.round((spent / budget) * 100));
}

function barColor(p: number) {
  if (p >= 100) return C.red;
  if (p >= 80) return C.deepOrange;
  return C.orange;
}

function SpentBar({ spent, budget }: { spent: number; budget: number | null }) {
  const p = pct(spent, budget);
  if (p == null) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <div
        style={{
          height: 6,
          borderRadius: 3,
          background: C.track,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${p}%`,
            borderRadius: 3,
            background:
              p >= 100 ? C.red : `linear-gradient(90deg, #6d6ae0, ${barColor(p)})`,
          }}
        />
      </div>
    </div>
  );
}

function SpendCard({
  label,
  spent,
  budget,
}: {
  label: string;
  spent: number;
  budget: number | null;
}) {
  const p = pct(spent, budget);
  return (
    <div
      style={{
        background: C.card,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
        padding: "10px 12px",
        marginBottom: 8,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <Typography.Text style={{ fontSize: 12, color: C.sub }}>{label}</Typography.Text>
        {p != null && (
          <Typography.Text style={{ fontSize: 11, color: C.faint }}>{p}%</Typography.Text>
        )}
      </div>
      <div style={{ marginTop: 2 }}>
        <Typography.Text strong style={{ fontSize: 15, color: C.text }}>
          {fmt(spent)}
          {budget != null && (
            <span style={{ color: C.faint, fontWeight: 400, fontSize: 12 }}>
              {" "}
              / {fmt(budget)}
            </span>
          )}
        </Typography.Text>
      </div>
      <SpentBar spent={spent} budget={budget} />
    </div>
  );
}

export default function UsagePanel() {
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api
      .getUsageSummary()
      .then(setData)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading) return <Spin style={{ padding: 16 }} />;

  if (!data) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={<span style={{ fontSize: 12, color: C.faint }}>暂无用量数据</span>}
      />
    );
  }

  const b = data.budget;
  const models = Object.entries(data.by_model_today);

  const status = b.over ? "over" : b.warning ? "warn" : "ok";
  const statusMeta = {
    ok: { text: "预算正常", color: C.green, bg: "#e9f6ee" },
    warn: { text: "接近预算", color: C.deepOrange, bg: "#eef0fe" },
    over: { text: "已超预算", color: C.red, bg: "#fdecea" },
  }[status];

  return (
    <div style={{ padding: "4px 2px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 10,
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "2px 8px",
            borderRadius: 10,
            background: statusMeta.bg,
            color: statusMeta.color,
            fontSize: 11,
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: statusMeta.color,
            }}
          />
          {statusMeta.text}
        </span>
        <Button size="small" type="text" icon={<ReloadOutlined />} onClick={load} />
      </div>

      <SpendCard label="本日花费" spent={b.daily_spent} budget={b.daily_budget} />
      <SpendCard label="本月花费" spent={b.monthly_spent} budget={b.monthly_budget} />

      <div style={{ padding: "2px 2px 4px" }}>
        <Typography.Text style={{ fontSize: 11, color: C.sub }}>
          Token 本日 {data.today.tokens_in} 入 / {data.today.tokens_out} 出
        </Typography.Text>
      </div>

      {models.length > 0 && (
        <div style={{ marginTop: 4 }}>
          <Typography.Text style={{ fontSize: 11, color: C.sub }}>按模型（本日）</Typography.Text>
          <div style={{ marginTop: 2 }}>
            {models.map(([m, v], i) => (
              <div
                key={m}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "4px 2px",
                  borderTop: i === 0 ? "1px solid #eef0f6" : "none",
                  borderBottom: "1px solid #eef0f6",
                }}
              >
                <Typography.Text style={{ fontSize: 11, color: C.faint }}>{m}</Typography.Text>
                <Typography.Text style={{ fontSize: 11, color: C.text }}>
                  {fmt(v.cost)}
                </Typography.Text>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}