import { useEffect, useState } from "react";
import { List, Tag, Typography, Spin, Empty } from "antd";
import { api, type SkillMeta } from "../lib/api";

export default function SkillsPanel() {
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getSkills()
      .then(setSkills)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin style={{ padding: 16 }} />;

  if (skills.length === 0) {
    return (
      <Empty
        style={{ marginTop: 40 }}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span style={{ fontSize: 12, color: "#8a857b" }}>
            暂无 Skill
            <br />
            在 ~/.config/myopencode/skills/ 或 .myopencode/skills/ 放置 SKILL.md
          </span>
        }
      />
    );
  }

  return (
    <List
      size="small"
      dataSource={skills}
      renderItem={(s) => (
        <List.Item style={{ padding: "10px 4px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Typography.Text strong style={{ fontSize: 13 }}>
                {s.name}
              </Typography.Text>
              <Tag
                style={{ fontSize: 10, lineHeight: "16px", margin: 0 }}
                color={s.source === "user" ? "default" : "orange"}
              >
                {s.source === "user" ? "用户" : "项目"}
              </Tag>
            </div>
            <Typography.Text
              style={{ fontSize: 12, color: "#8a857b", display: "block", marginTop: 2 }}
            >
              {s.description}
            </Typography.Text>
          </div>
        </List.Item>
      )}
    />
  );
}