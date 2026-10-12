"""记忆持久化存储：语义记忆 + 场景记忆，关键词 + 时间权重检索。"""
from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from .schema import EpisodicMemory, SemanticMemory, _now

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".config", "myopencode", "memory")


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _tokenize(text: str) -> List[str]:
    """按非字母数字切分，兼容中英文（中文按单字，英文/数字按词）。"""
    return re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", text.lower())


class MemoryStore:
    """管理语义/场景记忆的加载、保存、去重合并与检索。"""

    def __init__(self, directory: Optional[str] = None) -> None:
        self.directory = directory or DEFAULT_DIR
        self._facts: List[SemanticMemory] = []
        self._episodes: List[EpisodicMemory] = []

    # ── 持久化 ──────────────────────────────────────────────
    def load(self) -> None:
        self._facts = self._load_file("semantic.json", SemanticMemory)
        self._episodes = self._load_file("episodic.json", EpisodicMemory)

    def save(self) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
            self._save_file("semantic.json", [f.to_dict() for f in self._facts])
            self._save_file("episodic.json", [e.to_dict() for e in self._episodes])
        except OSError:
            pass

    def _load_file(self, name: str, cls: Any) -> List[Any]:
        path = os.path.join(self.directory, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return []
        out = []
        for item in data if isinstance(data, list) else []:
            try:
                out.append(cls.from_dict(item))
            except Exception:
                continue
        return out

    def _save_file(self, name: str, payload: List[Dict[str, Any]]) -> None:
        with open(os.path.join(self.directory, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    # ── 语义记忆 ────────────────────────────────────────────
    def add_fact(self, content: str, category: str = "general", importance: int = 3) -> SemanticMemory:
        content = (content or "").strip()
        if not content:
            raise ValueError("fact 内容不能为空")
        existing = next((f for f in self._facts if _similarity(f.content, content) >= 0.85), None)
        if existing is not None:
            existing.times_used += 1
            existing.updated_at = _now()
            if len(content) > len(existing.content):
                existing.content = content
            self.save()
            return existing
        fact = SemanticMemory(content=content, category=category, importance=importance)
        self._facts.append(fact)
        self._trim_facts()
        self.save()
        return fact

    def _trim_facts(self, max_facts: int = 200) -> None:
        if len(self._facts) <= max_facts:
            return
        self._facts.sort(key=lambda f: (f.importance, f.times_used, f.updated_at), reverse=True)
        self._facts = self._facts[:max_facts]

    def list_facts(self, limit: int = 100) -> List[SemanticMemory]:
        items = sorted(self._facts, key=lambda f: (f.importance, f.times_used, f.updated_at), reverse=True)
        return items[:limit]

    def search_facts(self, query: str = "", limit: int = 10) -> List[SemanticMemory]:
        """关键词检索：命中才返回（无关键词则返回按重要度排序的 top）。"""
        tokens = _tokenize(query or "")
        if not tokens:
            items = sorted(
                self._facts,
                key=lambda f: (f.importance, f.times_used, f.updated_at),
                reverse=True,
            )
            return items[:limit]
        scored: List[tuple] = []
        for f in self._facts:
            toks = set(_tokenize(f.content))
            hits = sum(1 for t in tokens if t in toks)
            if hits:
                score = hits * 10.0 + float(f.importance) + 0.5 * min(f.times_used, 10)
                scored.append((score, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:limit]]

    def delete_fact(self, fact_id: str) -> bool:
        for i, f in enumerate(self._facts):
            if f.id == fact_id:
                del self._facts[i]
                self.save()
                return True
        return False

    def mark_accessed(self, fact_id: str) -> None:
        for f in self._facts:
            if f.id == fact_id:
                f.last_accessed = _now()
                f.times_used += 1
                return

    # ── 场景记忆 ────────────────────────────────────────────
    def add_episode(
        self, session_id: str, title: str, summary: str, message_count: int = 0
    ) -> EpisodicMemory:
        ep = EpisodicMemory(
            session_id=session_id, title=title, summary=summary, message_count=message_count
        )
        ep.end_ts = _now()
        self._episodes.append(ep)
        self._trim_episodes()
        self.save()
        return ep

    def _trim_episodes(self, max_entries: int = 500) -> None:
        if len(self._episodes) <= max_entries:
            return
        self._episodes.sort(key=lambda e: e.end_ts, reverse=True)
        self._episodes = self._episodes[:max_entries]

    def list_episodes(self, limit: int = 50) -> List[EpisodicMemory]:
        items = sorted(self._episodes, key=lambda e: e.end_ts, reverse=True)
        return items[:limit]

    def search_episodes(self, query: str = "", limit: int = 5) -> List[EpisodicMemory]:
        """关键词检索：命中才返回（无关键词则返回最近 episode）。"""
        tokens = _tokenize(query or "")
        if not tokens:
            items = sorted(self._episodes, key=lambda e: e.end_ts, reverse=True)
            return items[:limit]
        max_ts = max((x.end_ts for x in self._episodes), default=1.0)
        scored: List[tuple] = []
        for e in self._episodes:
            toks = set(_tokenize(e.title + " " + e.summary))
            hits = sum(1 for t in tokens if t in toks)
            if hits:
                recency = (e.end_ts / max_ts) if max_ts > 0 else 0.0
                score = hits * 10.0 + recency
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def delete_episode(self, episode_id: str) -> bool:
        for i, e in enumerate(self._episodes):
            if e.id == episode_id:
                del self._episodes[i]
                self.save()
                return True
        return False