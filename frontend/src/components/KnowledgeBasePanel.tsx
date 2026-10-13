import { useEffect, useRef, useState } from "react";
import { Button, Input, List, Tag, Typography, Spin, Empty, message, Popconfirm, Divider } from "antd";
import { UploadOutlined, SearchOutlined, ReloadOutlined } from "@ant-design/icons";
import { api, type RagDoc, type RagQueryResult } from "../lib/api";

export default function KnowledgeBasePanel() {
  const [docs, setDocs] = useState<RagDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<RagQueryResult[]>([]);
  const [reindexing, setReindexing] = useState(false);
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
      const errors = r.results.filter((x) => x.error).map((x) => `${x.name}: ${x.error}`);
      if (done > 0) message.success(`已索引 ${done} 个文档`);
      if (skipped > 0) message.warning(`${skipped} 个文档跳过（重复或无法解析）`);
      if (errors.length > 0) {
        message.error(
          errors.slice(0, 3).join("；") + (errors.length > 3 ? ` 等 ${errors.length} 个` : ""),
          5,
        );
      }
      refresh();
    } catch (err) {
      message.error(`上传失败：${err instanceof Error ? err.message : String(err)}`);
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

  const onSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    try {
      const r = await api.ragQuery(q);
      setResults(r.results);
    } catch {
      message.error("检索失败");
    } finally {
      setSearching(false);
    }
  };

  const onReindex = async () => {
    setReindexing(true);
    try {
      const r = await api.ragReindex();
      message.success(`重建完成：${r.chunks} 块 / ${r.vectors} 向量`);
      refresh();
    } catch {
      message.error("重建索引失败");
    } finally {
      setReindexing(false);
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
        <Button size="small" icon={<ReloadOutlined />} loading={reindexing} onClick={onReindex}>
          重建索引
        </Button>
      </div>

      <Divider style={{ margin: "8px 0" }} />

      <Input.Search
        size="small"
        placeholder="检索测试（如：如何安装）"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onSearch={onSearch}
        enterButton={<SearchOutlined />}
        loading={searching}
        allowClear
      />

      {results.length > 0 && (
        <List
          size="small"
          style={{ marginTop: 8 }}
          dataSource={results}
          renderItem={(r, i) => (
            <List.Item style={{ padding: "8px 4px", display: "block" }}>
              <Typography.Text style={{ fontSize: 11, color: "#8b8da0" }}>
                [{i + 1}] 来源: {r.source} · {r.heading}（{r.score}）
              </Typography.Text>
              <Typography.Paragraph
                style={{ fontSize: 12, margin: "4px 0 0", whiteSpace: "pre-wrap" }}
                ellipsis={{ rows: 3, expandable: true, symbol: "展开" }}
              >
                {r.text}
              </Typography.Paragraph>
            </List.Item>
          )}
        />
      )}

      <Divider style={{ margin: "12px 0 8px" }} />

      {loading ? (
        <Spin style={{ padding: 16 }} />
      ) : docs.length === 0 ? (
        <Empty
          style={{ marginTop: 24 }}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={<span style={{ fontSize: 12, color: "#8b8da0" }}>知识库为空，上传文档开始构建</span>}
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