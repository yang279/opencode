import { useEffect, useRef, useState } from "react";
import { Button, List, Tag, Typography, Spin, Empty, message, Popconfirm } from "antd";
import { UploadOutlined } from "@ant-design/icons";
import { api, type RagDoc } from "../lib/api";

export default function KnowledgeBasePanel() {
  const [docs, setDocs] = useState<RagDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => {
    setLoading(true);
    api
      .ragDocs()
      .then((r) => setDocs(r.docs))
      .catch(() => message.error("加载知识库失败"))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const onFiles = async (list: FileList | null) => {
    const files = Array.from(list ?? []);
    if (files.length === 0) return;
    setUploading(true);
    try {
      const r = await api.ragUpload(files);
      const done = r.results.filter((x) => !x.skipped).length;
      const skipped = r.results.filter((x) => x.skipped).length;
      if (done > 0) message.success(`已索引 ${done} 个文档`);
      if (skipped > 0) message.warning(`${skipped} 个文档跳过（重复或无法解析）`);
      refresh();
    } catch {
      message.error("上传失败");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onDelete = async (id: string) => {
    try {
      await api.ragDelete(id);
      refresh();
    } catch {
      message.error("删除失败");
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 12, display: "flex", gap: 8 }}>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".pdf,.docx,.md,.markdown,.txt,.py,.js,.ts,.tsx,.jsx,.rs,.go,.java,.c,.cpp,.h,.cs,.rb,.sh,.yml,.yaml,.json,.toml,.html,.css,.sql"
          style={{ display: "none" }}
          onChange={(e) => onFiles(e.target.files)}
        />
        <Button
          size="small"
          icon={<UploadOutlined />}
          loading={uploading}
          onClick={() => fileRef.current?.click()}
        >
          上传文档
        </Button>
        <Typography.Text style={{ fontSize: 11, color: "#8a857b", alignSelf: "center" }}>
          支持 PDF / Word / Markdown / 文本 / 代码
        </Typography.Text>
      </div>

      {loading ? (
        <Spin style={{ padding: 16 }} />
      ) : docs.length === 0 ? (
        <Empty
          style={{ marginTop: 24 }}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={<span style={{ fontSize: 12, color: "#8a857b" }}>知识库为空，上传文档开始构建</span>}
        />
      ) : (
        <List
          size="small"
          dataSource={docs}
          renderItem={(d) => (
            <List.Item
              style={{ padding: "10px 4px" }}
              actions={[
                <Popconfirm key="del" title="删除该文档？" onConfirm={() => onDelete(d.id)}>
                  <Button size="small" type="text" danger>
                    删除
                  </Button>
                </Popconfirm>,
              ]}
            >
              <div style={{ minWidth: 0 }}>
                <Typography.Text strong style={{ fontSize: 13 }} ellipsis>
                  {d.name}
                </Typography.Text>
                <div style={{ marginTop: 2 }}>
                  <Tag style={{ fontSize: 10, lineHeight: "16px", margin: 0 }}>{d.ext}</Tag>
                  <Tag style={{ fontSize: 10, lineHeight: "16px", margin: 0 }} color="orange">
                    {d.chunk_count} 块
                  </Tag>
                </div>
              </div>
            </List.Item>
          )}
        />
      )}
    </div>
  );
}
