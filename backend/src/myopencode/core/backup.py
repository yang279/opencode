"""备份与回退：写前快照 + journal，支持 /undo 手动回退文件改动。

每次 agent run() 视为一个「改动组」；组内文件写入前自动快照。
/undo 逆序恢复最近一个非空改动组（覆盖旧文件、删除新建文件）。
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from typing import Dict, List, Optional

from ..config.schema import BackupConfig


class BackupManager:
    def __init__(self, config: BackupConfig, base_dir: Optional[str] = None) -> None:
        self.config = config
        self.base = base_dir or os.path.join(
            os.path.expanduser("~"), ".config", "myopencode", "backups"
        )
        self._session: Optional[str] = None
        self._journal: Optional[Dict[str, object]] = None
        self._journal_path: Optional[str] = None
        self._active_gid: Optional[str] = None
        self._lock = threading.Lock()

    # ── 会话/组生命周期 ──────────────────────────────────────
    def set_session(self, session_id: str) -> None:
        self._session = session_id
        self._journal_path = os.path.join(self.base, session_id, "journal.json")
        self._journal = self._load_journal()
        self._active_gid = None

    def begin_group(self) -> None:
        if self._journal is None:
            return
        with self._lock:
            gid = uuid.uuid4().hex[:12]
            groups = self._journal.setdefault("groups", [])
            groups.append({"id": gid, "entries": []})
            self._active_gid = gid

    def end_group(self) -> None:
        """组内无改动则丢弃空组。"""
        if self._journal is None:
            return
        with self._lock:
            groups = self._journal.get("groups", [])
            if groups and not groups[-1].get("entries"):
                groups.pop()
            self._active_gid = None
            self._save()

    # ── 写前快照 ─────────────────────────────────────────────
    def before_write(self, path: str, existed: bool) -> Optional[str]:
        """文件被工具写前调用。existed=True 则快照原文件，否则记录为新建。"""
        if not self.config.enabled or self._journal is None or self._active_gid is None:
            return None
        with self._lock:
            groups = self._journal.get("groups", [])
            if not groups:
                return None
            group = groups[-1]
            if group.get("id") != self._active_gid:
                return None

            entry = {
                "path": os.path.realpath(path),
                "op": "modify" if existed else "create",
                "ref": None,
            }
            if existed:
                ref = uuid.uuid4().hex[:12] + "_" + os.path.basename(path)
                files_dir = os.path.join(os.path.dirname(self._journal_path), "files")
                os.makedirs(files_dir, exist_ok=True)
                shutil.copy2(entry["path"], os.path.join(files_dir, ref))
                entry["ref"] = ref
            group.setdefault("entries", []).append(entry)
            self._save()
            return entry.get("ref")

    # ── 回退 ─────────────────────────────────────────────────
    def undo_last(self) -> List[str]:
        """逆序恢复最近一个非空改动组，返回被还原的路径列表。"""
        if self._journal is None:
            return []
        with self._lock:
            groups = self._journal.get("groups", [])
            if not groups:
                return []
            group = groups.pop()
            restored: List[str] = []
            files_dir = os.path.join(os.path.dirname(self._journal_path), "files")
            for entry in reversed(group.get("entries", [])):
                path = entry["path"]
                if entry.get("op") == "modify" and entry.get("ref"):
                    src = os.path.join(files_dir, entry["ref"])
                    if os.path.exists(src):
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        shutil.copy2(src, path)
                        os.remove(src)
                        restored.append(path)
                elif entry.get("op") == "create":
                    if os.path.exists(path):
                        os.remove(path)
                        restored.append(path)
            self._save()
        return restored

    def purge_session(self, session_id: Optional[str] = None) -> None:
        sid = session_id or self._session
        if sid:
            shutil.rmtree(os.path.join(self.base, sid), ignore_errors=True)

    # ── 持久化 ───────────────────────────────────────────────
    def _load_journal(self) -> Dict[str, object]:
        try:
            with open(self._journal_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {"groups": []}
        except (OSError, json.JSONDecodeError):
            return {"groups": []}

    def _save(self) -> None:
        if self._journal is None or self._journal_path is None:
            return
        try:
            os.makedirs(os.path.dirname(self._journal_path), exist_ok=True)
            with open(self._journal_path, "w", encoding="utf-8") as fh:
                json.dump(self._journal, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass