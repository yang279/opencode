import { useEffect, useState } from "react";
import { Modal, Form, Input, Select, Switch, InputNumber, Divider, Typography, message, Slider, Upload, Button } from "antd";
import { UploadOutlined, DeleteOutlined } from "@ant-design/icons";
import { api, type AppConfig } from "../lib/api";
import { useBackground } from "../hooks/useBackground";

const SANDBOX_BACKENDS = [
  { label: "自动", value: "auto" },
  { label: "容器 (Docker/podman)", value: "container" },
  { label: "seatbelt (macOS)", value: "seatbelt" },
  { label: "路径护栏", value: "pathguard" },
  { label: "关闭", value: "none" },
];

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

const PROVIDERS = ["openai", "anthropic", "ollama"];

const DEFAULT_MODELS: Record<string, string> = {
  openai: "deepseek-v4-pro",
  anthropic: "claude-3-5-sonnet-latest",
  ollama: "llama3",
};

export default function ConfigModal({ open, onClose, onSaved }: Props) {
  const [form] = Form.useForm();
  const bg = useBackground();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [baseConfig, setBaseConfig] = useState<AppConfig | null>(null);
  const provider: string = Form.useWatch("provider", form) ?? "openai";

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api
      .getConfig()
      .then((cfg) => {
        setBaseConfig(cfg);
        const pc = cfg.providers[cfg.provider] ?? {};
        form.setFieldsValue({
          provider: cfg.provider,
          model: cfg.model ?? pc.model ?? DEFAULT_MODELS[cfg.provider] ?? "",
          api_key: "",
          base_url: pc.base_url ?? (cfg.provider === "ollama" ? "http://localhost:11434/v1" : ""),
          intent_enabled: cfg.intent?.enabled ?? true,
          intent_model: cfg.intent?.model ?? "",
          sandbox_enabled: cfg.sandbox?.enabled ?? true,
          sandbox_backend: cfg.sandbox?.backend ?? "auto",
          sandbox_allow_network: cfg.sandbox?.allow_network ?? false,
          sandbox_image: cfg.sandbox?.container?.image ?? "myopencode-sandbox:latest",
          backup_enabled: cfg.backup?.enabled ?? true,
          daily_budget_usd: cfg.llm?.daily_budget_usd ?? null,
          monthly_budget_usd: cfg.llm?.monthly_budget_usd ?? null,
          budget_hard_stop: cfg.llm?.budget_hard_stop ?? true,
        });
      })
      .catch((e) => message.error(String(e)))
      .finally(() => setLoading(false));
  }, [open, form]);

  const submit = async () => {
    if (!baseConfig) return;
    const values = await form.validateFields();
    const p = values.provider as string;
    const next: AppConfig = {
      ...baseConfig,
      provider: p,
      model: values.model || null,
      providers: {
        ...baseConfig.providers,
        [p]: {
          api_key: values.api_key?.trim() || null,
          base_url: values.base_url || null,
          model: values.model || null,
        },
      },
      intent: {
        ...(baseConfig.intent ?? { enabled: true }),
        enabled: values.intent_enabled ?? true,
        model: values.intent_model?.trim() || null,
      },
      sandbox: {
        ...(baseConfig.sandbox ?? { enabled: true, allow_network: false }),
        enabled: values.sandbox_enabled ?? true,
        backend: values.sandbox_backend ?? "auto",
        allow_network: values.sandbox_allow_network ?? false,
        container: {
          ...(baseConfig.sandbox?.container ?? {}),
          image: values.sandbox_image?.trim() || "myopencode-sandbox:latest",
        },
      },
      backup: {
        ...(baseConfig.backup ?? { enabled: true }),
        enabled: values.backup_enabled ?? true,
      },
      llm: {
        ...(baseConfig.llm ?? {}),
        daily_budget_usd: values.daily_budget_usd ?? null,
        monthly_budget_usd: values.monthly_budget_usd ?? null,
        budget_hard_stop: values.budget_hard_stop ?? true,
      },
    };
    setSaving(true);
    try {
      await api.updateConfig(next);
      message.success("已保存并生效");
      onSaved();
      onClose();
    } catch (e) {
      message.error(String(e));
    } finally {
      setSaving(false);
    }
  };

  const showApiKey = provider === "openai" || provider === "anthropic";
  const showBaseUrl =
    provider === "openai" || provider === "anthropic" || provider === "ollama";

  return (
    <Modal
      open={open}
      title="模型配置"
      onCancel={onClose}
      onOk={submit}
      okText="保存"
      cancelText="取消"
      confirmLoading={saving}
      width={440}
      centered
      styles={{
        body: { maxHeight: "calc(100vh - 200px)", overflowY: "auto", scrollbarGutter: "stable" },
      }}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 12 }} disabled={loading}>
        <Form.Item name="provider" label="Provider" rules={[{ required: true }]}>
          <Select
            options={PROVIDERS.map((p) => ({ label: p, value: p }))}
            onChange={(p) => {
              const cur = form.getFieldValue("model");
              if (!cur) form.setFieldValue("model", DEFAULT_MODELS[p] ?? "");
              if (p === "ollama") form.setFieldValue("base_url", "http://localhost:11434/v1");
            }}
          />
        </Form.Item>

        <Form.Item name="model" label="模型" rules={[{ required: true, message: "请填写模型名" }]}>
          <Input placeholder={DEFAULT_MODELS[provider] ?? "gpt-4o"} />
        </Form.Item>

        {showApiKey && (
          <Form.Item name="api_key" label="API Key">
            <Input.Password autoComplete="new-password" placeholder="留空则保持原 key 不变" />
          </Form.Item>
        )}

        {showBaseUrl && (
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
        )}

        <Divider style={{ margin: "16px 0 8px" }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <Typography.Text strong style={{ fontSize: 13 }}>意图识别</Typography.Text>
          <Form.Item name="intent_enabled" valuePropName="checked" noStyle>
            <Switch size="small" />
          </Form.Item>
        </div>
        <Form.Item name="intent_model" label="意图识别模型">
          <Input placeholder="留空使用小模型（默认 qwen3.8-flash）" />
        </Form.Item>

        <Divider style={{ margin: "16px 0 8px" }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <Typography.Text strong style={{ fontSize: 13 }}>沙箱隔离</Typography.Text>
          <Form.Item name="sandbox_enabled" valuePropName="checked" noStyle>
            <Switch size="small" />
          </Form.Item>
        </div>
        <Form.Item name="sandbox_backend" label="沙箱后端">
          <Select options={SANDBOX_BACKENDS} />
        </Form.Item>
        <Form.Item name="sandbox_image" label="容器镜像">
          <Input placeholder="myopencode-sandbox:latest" />
        </Form.Item>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <Typography.Text style={{ fontSize: 13 }}>允许联网</Typography.Text>
          <Form.Item name="sandbox_allow_network" valuePropName="checked" noStyle>
            <Switch size="small" />
          </Form.Item>
        </div>

        <Divider style={{ margin: "16px 0 8px" }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <Typography.Text strong style={{ fontSize: 13 }}>文件备份（支持 /undo）</Typography.Text>
          <Form.Item name="backup_enabled" valuePropName="checked" noStyle>
            <Switch size="small" />
          </Form.Item>
        </div>

        <Divider style={{ margin: "16px 0 8px" }} />
        <Typography.Text strong style={{ fontSize: 13, display: "block", marginBottom: 8 }}>
          成本预算
        </Typography.Text>
        <Form.Item name="daily_budget_usd" label="每日预算 (USD，留空不限额)">
          <InputNumber min={0} step={0.1} style={{ width: "100%" }} placeholder="不限" />
        </Form.Item>
        <Form.Item name="monthly_budget_usd" label="每月预算 (USD，留空不限额)">
          <InputNumber min={0} step={1} style={{ width: "100%" }} placeholder="不限" />
        </Form.Item>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
          <Typography.Text style={{ fontSize: 13 }}>超限硬停当前任务</Typography.Text>
          <Form.Item name="budget_hard_stop" valuePropName="checked" noStyle>
            <Switch size="small" />
          </Form.Item>
        </div>
      </Form>

      <Divider style={{ margin: "16px 0 8px" }} />
      <Typography.Text strong style={{ fontSize: 13, display: "block", marginBottom: 8 }}>
        外观
      </Typography.Text>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Upload
          accept="image/png,image/jpeg,image/webp,image/gif"
          showUploadList={false}
          beforeUpload={async (file) => {
            try {
              await bg.upload(file);
              message.success("背景图已更新");
            } catch (e) {
              message.error(String(e));
            }
            return false;
          }}
        >
          <Button icon={<UploadOutlined />}>上传背景图</Button>
        </Upload>
        {bg.dataUrl && (
          <img
            src={bg.dataUrl}
            alt="背景预览"
            style={{ width: 64, height: 40, borderRadius: 6, objectFit: "cover", border: "1px solid #e4e5ee" }}
          />
        )}
        {bg.dataUrl && (
          <Button
            danger
            icon={<DeleteOutlined />}
            onClick={async () => {
              try {
                await bg.remove();
                message.success("已移除背景图");
              } catch (e) {
                message.error(String(e));
              }
            }}
          >
            移除
          </Button>
        )}
      </div>
      <div style={{ marginTop: 8 }}>
        <Typography.Text style={{ fontSize: 13 }}>模糊度</Typography.Text>
        <Slider min={0} max={40} value={bg.blur} onChange={bg.setBlur} />
      </div>
      <div>
        <Typography.Text style={{ fontSize: 13 }}>暗化度</Typography.Text>
        <Slider min={0} max={80} value={bg.dark} onChange={bg.setDark} />
      </div>
    </Modal>
  );
}