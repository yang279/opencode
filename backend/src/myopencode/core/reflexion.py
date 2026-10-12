"""Reflexion 外层：整轮尝试结束后判定结果、生成自我批评、预算内重试。

- judge：可配置 verifier（error_free / verify_command / llm / none）
- critique：调用 LLM 生成"为什么没成功 + 如何改进"的简短反思
- 反思结果由 agent 以「反思」消息回填进下一轮尝试的上下文
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from ..config.schema import ReflexionConfig
from ..core.session import Message, Session
from ..llm.base import LLMProvider

_CATEGORY_CODE = ("code_edit", "code_read", "execute")


@dataclass
class Verdict:
    success: bool
    reason: str = ""


class ReflexionController:
    def __init__(
        self,
        config: ReflexionConfig,
        provider: LLMProvider,
        budget: Any = None,
        metrics: Any = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.budget = budget
        self.metrics = metrics

    def allow_retry(self, attempt: int) -> bool:
        """是否允许再来一次尝试（预算护栏联动）。"""
        if not self.config.enabled:
            return False
        if attempt >= self.config.max_attempts:
            return False
        if self.config.budget_aware and self.budget is not None:
            if self.budget.status().get("over"):
                return False
        return True

    async def judge(
        self,
        state: Any,
        errored: bool,
        category: Optional[str],
        sandbox: Any,
        verify_command: Optional[str],
    ) -> Verdict:
        """判定一次尝试是否成功。取消/拒绝直接判失败（不再重试由上层决定）。"""
        if state.cancelled or state.rejected:
            return Verdict(False, "已取消或拒绝")

        verifier = self.config.verifier
        if verifier == "none":
            return Verdict(True)
        if verifier == "llm":
            return await self._llm_judge(state)
        if verifier in ("verify_command", "auto") and verify_command and category in _CATEGORY_CODE:
            ok = await self._run_verify(verify_command, sandbox)
            return Verdict(ok, "" if ok else "验证命令未通过")
        # 默认 error_free
        return Verdict(not errored, "" if not errored else "存在工具执行错误")

    async def _run_verify(self, command: str, sandbox: Any) -> bool:
        argv = sandbox.wrap_shell(command) if sandbox is not None else ["/bin/bash", "-lc", command]
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception:  # pragma: no cover
            return False
        try:
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except asyncio.TimeoutError:
            return False
        return proc.returncode == 0

    async def _llm_judge(self, state: Any) -> Verdict:
        transcript = _transcript(state.session)
        answer = await self._complete(
            "你是任务完成度判定器。根据对话内容判断任务是否已成功完成。只输出 yes 或 no。",
            transcript[:4000],
            self.config.critique_timeout,
        )
        if answer.strip().lower().startswith("yes"):
            return Verdict(True)
        return Verdict(False, "LLM 判定未完成")

    async def critique(self, session: Session) -> str:
        """生成自我批评：哪里没做对、下一轮如何改进。"""
        if not self.config.use_critique:
            return ""
        transcript = _transcript(session)
        if not transcript:
            return ""
        return await self._complete(
            "你是反思助手。根据这段对话，用中文简要总结：任务为什么没成功完成、下一步应该怎样改进。只输出反思内容，不超过 200 字。",
            transcript[:6000],
            self.config.critique_timeout,
        )

    async def _complete(self, system: str, user: str, timeout: float) -> str:
        msgs = [
            Message(role="system", content=system),
            Message(role="user", content=user),
        ]
        parts = []

        async def _drain() -> None:
            async for ev in self.provider.stream(msgs, []):
                if ev.kind == "text" and ev.delta:
                    parts.append(ev.delta)

        try:
            await asyncio.wait_for(_drain(), timeout=timeout)
        except Exception:  # pragma: no cover
            pass
        return "".join(parts).strip()


def _transcript(session: Session) -> str:
    lines = []
    for m in session.messages:
        if m.role == "system":
            continue
        content = (m.content or "").strip()
        if m.role == "tool":
            content = content[:500]
        if content:
            lines.append("[{}] {}".format(m.role, content))
    return "\n".join(lines)