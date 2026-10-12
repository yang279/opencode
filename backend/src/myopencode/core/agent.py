"""Agent 主循环：LLM → 工具 → 审批 → 结果回填，直到纯文本结束。

Agent 无状态（不持有 session），每次 run 传入目标 Session，支持多会话并发。
每次 run 生成独立的 RunState（policy/sandbox/backup/cancel_token 等可变状态），
避免并发会话互相污染；共享依赖（provider/tools/config/emit/memory/intent）只读复用。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..config.schema import AppConfig
from ..core.backup import BackupManager
from ..core.errors import ErrorCode
from ..core.observability import redact
from ..intent.pipeline import IntentPipeline
from ..llm.base import LLMProvider
from ..llm.budget import BudgetExceededError
from ..llm.registry import create_fallback_providers
from ..llm.retry import resilient_stream
from ..security.policy import APPROVE_ALWAYS, REJECT, PermissionPolicy
from ..security.safety import SEVERITY_HIGH, SEVERITY_MEDIUM
from ..memory.manager import MemoryManager
from ..tools.base import ProcessTracker, ToolContext, ToolResult
from ..tools.pathguard import PathDeniedError
from ..tools.registry import ToolRegistry
from ..tools.sandbox import Sandbox
from . import events as E
from . import tracing
from .alerts import send_alert
from .planner import Planner
from .session import ApprovalItem, Message, QuestionItem, SafetyItem, Session

_logger = logging.getLogger("myopencode.agent")

# 主循环提问约定：需要用户输入时先用 ask_user 并立即停下，不先跑工具/答题
_ASK_USER_GUIDANCE = (
    "当需要用户澄清、确认或补充信息时，请立即调用 ask_user 工具提问，"
    "并在本轮只做这一件事（不要先执行其它工具，也不要自行输出答案或猜测），"
    "调用后立即停止输出，等待用户回答。"
    "如有候选选项，用 ask_user 的 options 字段给出（可用 recommended 标推荐项，"
    "multi 设为 true 允许多选），让用户点选或自填。"
)

# 事件发送回调：把事件 dict 推给前端
EventSink = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class RunState:
    """单次 run 的可变状态：并发会话各自独立，互不污染。"""

    session: Session
    policy: PermissionPolicy
    sandbox: Any
    backup: Any
    cancelled: bool = False
    rejected: bool = False
    cancel_token: Optional[ProcessTracker] = None
    active_tools: Optional[List[str]] = None
    intent_section: str = ""
    last_intent_category: Optional[str] = None
    skill_content: str = ""


class Agent:
    def __init__(
        self,
        config: AppConfig,
        provider: LLMProvider,
        tools: ToolRegistry,
        policy: Optional[PermissionPolicy] = None,
        emit: Optional[EventSink] = None,
        skills_section: str = "",
        memory: Optional[MemoryManager] = None,
        intent: Optional[IntentPipeline] = None,
        sandbox: Any = None,
        backup: Any = None,
        metrics: Any = None,
        audit: Any = None,
        safety: Any = None,
        content_filter: Any = None,
        budget: Any = None,
        skills: Any = None,
        reflexion: Any = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.tools = tools
        self.emit = emit
        self._skills_section = skills_section
        self._skills_registry = skills
        self._reflexion = reflexion
        self._memory = memory
        self._intent = intent
        self._metrics = metrics
        self._audit = audit
        self._safety = safety
        self._content_filter = content_filter
        self._budget = budget
        self._budget_warned = False
        self._fallbacks = create_fallback_providers(config)
        self._planner = Planner(provider, config.planning, config.llm, self._fallbacks)
        self._active_runs: Dict[str, RunState] = {}

    # ── 热更新支持（PUT /config 时切换 provider / config / intent）──
    # policy/sandbox/backup 不再作为实例态缓存，改为每次 run 从 config 现建，
    # 因此热更新只需刷新 config/provider/intent，运行中的 run 用旧快照不受影响。
    def set_provider(self, provider: LLMProvider) -> None:
        self.provider = provider

    def set_config(self, config: AppConfig) -> None:
        self.config = config
        self._fallbacks = create_fallback_providers(config)
        self._planner = Planner(self.provider, config.planning, config.llm, self._fallbacks)

    def set_intent(self, intent: Optional[IntentPipeline]) -> None:
        self._intent = intent

    def set_safety(self, safety: Any) -> None:
        self._safety = safety

    def set_content_filter(self, content_filter: Any) -> None:
        self._content_filter = content_filter

    def set_budget(self, budget: Any) -> None:
        self._budget = budget

    def set_reflexion(self, reflexion: Any) -> None:
        self._reflexion = reflexion

    async def _check_budget(self, session: Session) -> None:
        """LLM 调用前检查预算：超限硬停（或仅告警），接近上限告警。"""
        if self._budget is None:
            return
        status = self._budget.status()
        if status["warning"] and not status["over"] and not self._budget_warned:
            self._budget_warned = True
            await self._emit(session, E.budget_warning(status))
            self._schedule_alert("budget_warning", status)
        if status["over"]:
            await self._emit(session, E.budget_exceeded(status))
            self._schedule_alert("budget_exceeded", status)
            if status.get("hard_stop", True):
                raise BudgetExceededError(self._budget.message(status))

    def _schedule_alert(self, event: str, status: Dict[str, Any]) -> None:
        """预算告警 webhook（fire-and-forget）。"""
        url = getattr(self.config.observability, "alert_webhook_url", None)
        if not url:
            return
        asyncio.create_task(send_alert(url, event, status))

    def _build_state(self, session: Session) -> RunState:
        return RunState(
            session=session,
            policy=PermissionPolicy(self.config.permissions),
            sandbox=Sandbox(self.config.sandbox, self.config.working_dir),
            backup=BackupManager(self.config.backup),
            cancel_token=ProcessTracker(),
        )

    def _schedule_finalize(self, session: Session) -> None:
        """后台固化记忆（fire-and-forget），不阻塞 run 完成。

        否则 done 已 emit、但 run 尚未返回，后端会把该会话误判为「仍在运行」，
        导致紧接着的下一条消息被拒。summarizer 已带超时兜底。
        """
        if self._memory is None:
            return

        async def _job() -> None:
            try:
                await self._memory.finalize_session(session)
            except Exception:  # pragma: no cover
                pass

        asyncio.create_task(_job())

    def cancel(self, session_id: Optional[str] = None) -> None:
        """取消运行中的任务。session_id 为 None 时取消全部；否则只取消目标会话。"""
        if session_id is not None:
            state = self._active_runs.get(session_id)
            if state is not None:
                state.cancelled = True
                if state.cancel_token is not None:
                    state.cancel_token.kill()
            return
        for state in self._active_runs.values():
            state.cancelled = True
            if state.cancel_token is not None:
                state.cancel_token.kill()

    async def _emit(self, session: Session, event: Dict[str, Any]) -> None:
        if self.emit is None:
            return
        event = dict(event)
        event["session_id"] = session.session_id
        await self.emit(event)

    async def run(self, session: Session, user_content: str) -> None:
        state = self._build_state(session)
        self._active_runs[session.session_id] = state
        try:
            if self._metrics is not None:
                self._metrics.incr("agent_run_total")
            start = time.perf_counter()
            with tracing.span("agent.run", logger=_logger):
                await self._run_impl(state, user_content)
            if self._metrics is not None:
                self._metrics.observe_histogram("agent_run_seconds", time.perf_counter() - start)
        finally:
            self._active_runs.pop(session.session_id, None)

    async def _run_impl(self, state: RunState, user_content: str) -> None:
        session = state.session
        state.cancelled = False
        state.rejected = False
        state.cancel_token = ProcessTracker()
        session.append(Message(role="user", content=user_content))
        if not session.title or session.title == "新对话":
            session.title = user_content.strip()[:30] or "新对话"
        state.active_tools = None
        state.intent_section = ""
        state.last_intent_category = None
        session.execution_state = {"active": True, "round": 0}
        if state.backup is not None:
            state.backup.set_session(session.session_id)
            state.backup.begin_group()
        if (
            state.sandbox is not None
            and self.config.sandbox.enabled
            and state.sandbox.backend_name == "pathguard"
            and self.config.sandbox.backend not in ("pathguard", "none")
        ):
            await self._emit(
                session,
                E.degraded("沙箱已降级到 pathguard（无 OS 隔离），请检查 Docker/sandbox-exec"),
            )
        await self._emit(session, E.progress("intent", "正在理解意图…"))
        await self._recognize_intent(state, user_content)
        await self._dispatch_skill(state, user_content)
        self._budget_warned = False
        try:
            try:
                await self._check_budget(session)
                if self._safety is not None and self.config.safety.enabled:
                    verdicts = await self._safety.check_user(user_content)
                    if verdicts:
                        decision = await self._request_safety(session, verdicts)
                        if decision != "continue":
                            state.rejected = True
                            state.cancelled = True
                            await self._emit(session, E.error("已按安全策略停止本次执行"))
                            await self._emit(session, E.done())
                            return
                await self._run_episode(state)
                if not state.cancelled and self._memory is not None:
                    self._schedule_finalize(session)
            except asyncio.CancelledError:
                await self._emit(session, E.done())
                raise
            except BudgetExceededError:
                if self._metrics is not None:
                    self._metrics.incr("budget_exceeded_total")
                await self._emit(
                    session, E.error("预算超限，本次任务已停止", ErrorCode.BUDGET_EXCEEDED)
                )
                await self._emit(session, E.done())
            except Exception as exc:
                if self._metrics is not None:
                    self._metrics.incr("agent_error_total")
                await self._emit(session, E.error("运行出错: {}".format(exc)))
                await self._emit(session, E.done())
        finally:
            # 唤醒并清理该会话所有待审批项/待回答提问/挂起安全确认，避免残留
            for item in list(session.pending_approvals.values()):
                if not item.future.done():
                    item.future.set_result(REJECT)
            for item in list(session.pending_questions.values()):
                if not item.future.done():
                    item.future.set_result("")
            for item in list(session.pending_safety.values()):
                if not item.future.done():
                    item.future.set_result("abort")
            if state.backup is not None:
                state.backup.end_group()
            state.cancel_token = None
            if state.rejected or not state.cancelled:
                session.execution_state = None

    async def _run_episode(self, state: RunState) -> None:
        """单次 ReAct 尝试（复用 _loop），并按 Reflexion 配置做失败重试。"""
        session = state.session
        if self._reflexion is None:
            await self._loop(state, final=True)
            return

        attempt = 0
        while True:
            attempt += 1
            if state.cancelled:
                break
            errored = await self._loop(state, final=False)
            verdict = await self._reflexion.judge(
                state,
                errored,
                state.last_intent_category,
                state.sandbox,
                self.config.planning.verify_command,
            )
            if verdict.success:
                break
            if not self._reflexion.allow_retry(attempt):
                break
            critique = await self._reflexion.critique(session)
            if self._metrics is not None:
                self._metrics.incr("reflexion_retry_total")
            await self._emit(session, E.reflection(attempt, critique))
            session.append(
                Message(
                    role="user",
                    content="上一轮未成功完成。反思：{}\n请据此修正并重新完成任务。".format(
                        critique or "请重试"
                    ),
                )
            )
        await self._emit(session, E.done())

    # ── 模型驱动编排：plan / delegate 工具（agent 层拦截实现）────
    async def _run_plan_tool(self, state: RunState, args: Dict[str, Any]) -> ToolResult:
        """plan 工具：拆解任务为带依赖的步骤，返回步骤清单文本供模型后续执行。"""
        session = state.session
        task = str(args.get("task", "")).strip()
        if not task:
            return ToolResult(output="plan 需要 task 参数", error=True)
        await self._emit(session, E.progress("plan", "正在制定计划…"))
        steps = await self._planner.plan(task)
        if not steps:
            return ToolResult(output="未能拆解出步骤，请直接执行。")
        step_data = [s.to_dict() for s in steps]
        await self._emit(session, E.plan(step_data))
        _logger.info(
            "plan.created", extra={"count": len(steps), "titles": [s.title for s in steps]}
        )
        text = "\n".join(
            "- [{}] {}: {}".format(s.id, s.title, s.description) for s in steps
        )
        return ToolResult(output="已生成 {} 个步骤：\n{}".format(len(steps), text))

    async def _run_delegate_tool(
        self, state: RunState, args: Dict[str, Any], pol: PermissionPolicy
    ) -> ToolResult:
        """delegate 工具：并行派多个子代理执行互不依赖的子任务，返回结果摘要。"""
        session = state.session
        if pol.delegated:
            return ToolResult(output="子任务不能再派并行子代理。", error=True)
        tasks = args.get("tasks") or []
        if isinstance(tasks, str):
            tasks = [tasks]
        tasks = [str(t).strip() for t in tasks if str(t).strip()]
        if not tasks:
            return ToolResult(output="delegate 需要 tasks 列表", error=True)
        max_par = self.config.planning.max_parallel or 3
        tasks = tasks[:max_par]

        delegated = self._delegated_policy()

        async def _one(idx: int, desc: str) -> str:
            if state.cancelled:
                return "（已取消）"
            title = "任务{}".format(idx + 1)
            await self._emit(session, E.progress("step", "并行：{}".format(desc[:40])))
            scratch = Session(session_id=session.session_id, title=session.title)
            scratch.append(Message(role="user", content="子任务：{}".format(desc)))
            tracker = ProcessTracker()
            await self._loop(
                state, final=False, session=scratch, tracker=tracker, policy=delegated
            )
            return "【{}】{}".format(title, self._summarize_scratch(scratch))

        await self._emit(session, E.progress("step", "并行执行 {} 个子任务…".format(len(tasks))))
        results = await asyncio.gather(*(_one(i, t) for i, t in enumerate(tasks)))
        return ToolResult(output="\n\n".join(results))

    def _delegated_policy(self) -> PermissionPolicy:
        """并行子 agent 用的委托策略：不弹审批，但保留命令 allow/deny 语义。"""
        return PermissionPolicy(self.config.permissions, delegated=True)

    def _summarize_scratch(self, scratch: Session) -> str:
        texts = [m.content for m in scratch.messages if m.role == "assistant" and m.content]
        if texts:
            return texts[-1][:300] or "已完成"
        return "已执行工具调用"

    async def resume(self, session: Session) -> None:
        """从中断点继续一个未完成会话（execution_state.active=True）。"""
        state = self._build_state(session)
        self._active_runs[session.session_id] = state
        try:
            await self._resume_impl(state)
        finally:
            self._active_runs.pop(session.session_id, None)

    async def _resume_impl(self, state: RunState) -> None:
        session = state.session
        prev = session.execution_state or {}
        if not prev.get("active"):
            await self._emit(session, E.error("该会话没有可继续的任务"))
            await self._emit(session, E.done())
            return
        state.cancelled = False
        state.rejected = False
        state.cancel_token = ProcessTracker()
        state.active_tools = prev.get("active_tools")
        if state.backup is not None:
            state.backup.set_session(session.session_id)
            state.backup.begin_group()
        try:
            try:
                await self._run_episode(state)
                if not state.cancelled and self._memory is not None:
                    self._schedule_finalize(session)
            except asyncio.CancelledError:
                await self._emit(session, E.done())
                raise
            except Exception as exc:
                await self._emit(session, E.error("运行出错: {}".format(exc)))
                await self._emit(session, E.done())
        finally:
            for item in list(session.pending_approvals.values()):
                if not item.future.done():
                    item.future.set_result(REJECT)
            for item in list(session.pending_questions.values()):
                if not item.future.done():
                    item.future.set_result("")
            if state.backup is not None:
                state.backup.end_group()
            state.cancel_token = None
            if state.rejected or not state.cancelled:
                session.execution_state = None

    async def _loop(
        self,
        state: RunState,
        final: bool = True,
        session: Optional[Session] = None,
        tracker: Optional[ProcessTracker] = None,
        policy: Optional[PermissionPolicy] = None,
    ) -> bool:
        """ReAct 内循环。返回是否有任何工具报错（供验证/重试使用）。"""
        session = session or state.session
        max_rounds = 20
        tracker = tracker or state.cancel_token
        pol = policy or state.policy
        errored = False

        async def _done() -> None:
            if final:
                await self._emit(session, E.done())

        for round_idx in range(max_rounds):
            if state.cancelled:
                break
            await self._check_budget(session)
            session.execution_state = {
                "active": True,
                "round": round_idx,
                "active_tools": state.active_tools,
            }
            messages = await self._build_messages(state, session)
            tool_calls: List[Dict[str, Any]] = []
            text_parts: List[str] = []

            async for ev in resilient_stream(
                [self.provider, *self._fallbacks],
                messages,
                self.tools.schemas(state.active_tools),
                self.config.llm,
                max_tokens=self.config.llm.per_request_max_tokens,
                on_degraded=lambda msg: self._emit(session, E.degraded(msg)),
            ):
                if state.cancelled:
                    await _done()
                    return errored
                if ev.kind == "text" and ev.delta:
                    text_parts.append(ev.delta)
                    await self._emit(session, E.assistant_text(redact(ev.delta)))
                elif ev.kind == "tool_call" and ev.tool_name:
                    tool_calls.append(
                        {
                            "id": ev.tool_id or "call_{}".format(uuid.uuid4().hex[:8]),
                            "name": ev.tool_name,
                            "arguments": ev.tool_arguments or "{}",
                        }
                    )

            if not tool_calls:
                # 纯文本回复，持久化到会话历史
                if text_parts:
                    final_text = redact("".join(text_parts))
                    session.append(Message(role="assistant", content=final_text))
                    if self._content_filter is not None and self._content_filter.enabled:
                        if await self._content_filter.check(final_text):
                            await self._emit(
                                session, E.content_flag("内容可能违反安全策略，请谨慎参考")
                            )
                await _done()
                return errored

            session.append(
                Message(
                    role="assistant",
                    content=redact("".join(text_parts)),
                    tool_calls=[
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in tool_calls
                    ],
                )
            )

            for tc in tool_calls:
                if state.cancelled:
                    await _done()
                    return errored
                err = await self._run_tool(
                    state, session, tc["id"], tc["name"], tc["arguments"],
                    tracker=tracker, policy=pol,
                )
                errored = errored or err

        await _done()
        return errored

    async def _run_tool(
        self,
        state: RunState,
        session: Session,
        tool_id: str,
        name: str,
        raw_args: str,
        tracker: Optional[ProcessTracker] = None,
        policy: Optional[PermissionPolicy] = None,
    ) -> bool:
        tracker = tracker or state.cancel_token
        pol = policy or state.policy
        args = self._parse_args(raw_args)

        if name == "ask_user":
            if pol.delegated:
                result = ToolResult(
                    output="并行子任务不能向用户提问，请基于现有信息自行决定并继续。",
                    error=False,
                )
                session.append(
                    Message(role="tool", content=result.output, tool_call_id=tool_id, name=name)
                )
                return False
            answer = await self._request_answer(session, args)
            result = self._sanitize_result(ToolResult(output=answer))
            session.append(
                Message(role="tool", content=result.output, tool_call_id=tool_id, name=name)
            )
            return False

        if name == "plan":
            await self._emit(session, E.tool_call_start(tool_id, name, args))
            result = self._sanitize_result(await self._run_plan_tool(state, args))
            await self._finish_tool(session, tool_id, result)
            session.append(
                Message(role="tool", content=result.output, tool_call_id=tool_id, name=name)
            )
            return result.error

        if name == "delegate":
            await self._emit(session, E.tool_call_start(tool_id, name, args))
            result = self._sanitize_result(await self._run_delegate_tool(state, args, pol))
            await self._finish_tool(session, tool_id, result)
            session.append(
                Message(role="tool", content=result.output, tool_call_id=tool_id, name=name)
            )
            return result.error

        await self._emit(session, E.tool_call_start(tool_id, name, args))

        decision = "auto"

        # 命令级强制拦截：黑名单/白名单命中，硬拒且不再弹审批
        if name == "run_shell":
            deny_reason = pol.check_command(str(args.get("command", "")))
            if deny_reason:
                result = ToolResult(output="命令被策略拒绝: {}".format(deny_reason), error=True)
                await self._finish_tool(session, tool_id, result)
                if self._audit is not None:
                    self._audit.record("tool_call", tool=name, decision="deny", result_ok=False)
                return True

        reason = pol.needs_approval(name, args)
        if reason:
            decision = await self._request_approval(session, tool_id, name, args, reason)
            if decision == REJECT:
                result = ToolResult(output="用户拒绝了该操作", error=True)
                await self._finish_tool(session, tool_id, result)
                if self._audit is not None:
                    self._audit.record("tool_call", tool=name, decision=decision, result_ok=False)
                state.rejected = True
                state.cancelled = True
                return True
            if decision == APPROVE_ALWAYS:
                pol.mark_always(name)

        working_dir = state.sandbox.working_dir if state.sandbox else self.config.working_dir
        ctx = ToolContext(
            working_dir=working_dir,
            path_guard=state.sandbox.path_guard if state.sandbox else None,
            sandbox=state.sandbox,
            backup=state.backup,
            cancel_token=tracker,
            max_output_bytes=self.config.permissions.max_output_bytes,
            scrub_secrets=self.config.permissions.scrub_secrets,
        )
        with tracing.span("tool.call", logger=_logger, tool=name):
            try:
                result = await self.tools.execute(name, args, ctx)
            except KeyError as exc:
                result = ToolResult(output=str(exc), error=True)
            except PathDeniedError as exc:
                result = ToolResult(output=str(exc), error=True)
            except Exception as exc:  # pragma: no cover
                result = ToolResult(output="工具执行异常: {}".format(exc), error=True)
        result = self._sanitize_result(result)

        if (
            self._safety is not None
            and self.config.safety.enabled
            and self.config.safety.scan_tool_results
            and (name in ("read_file", "grep") or name.startswith("mcp_"))
        ):
            block_reason = self._safety.scan_tool_result(result.output)
            if block_reason:
                result = ToolResult(output=block_reason, error=True)

        if self._metrics is not None:
            self._metrics.incr("tool_call_total", tool=name)
            if result.error:
                self._metrics.incr("tool_error_total", tool=name)
        if self._audit is not None:
            files = [args.get("path")] if name in ("write_file", "edit_file") and args.get("path") else []
            self._audit.record(
                "tool_call",
                tool=name,
                decision=decision,
                result_ok=not result.error,
                files_changed=files,
            )
        _logger.info(
            "tool.finished",
            extra={"tool": name, "result_ok": not result.error, "decision": decision},
        )

        await self._finish_tool(session, tool_id, result)
        session.append(
            Message(role="tool", content=result.output, tool_call_id=tool_id, name=name)
        )
        return result.error

    async def _finish_tool(self, session: Session, tool_id: str, result: ToolResult) -> None:
        await self._emit(session, E.tool_call_end(tool_id, result.output, result.diff))

    def _sanitize_result(self, result: ToolResult) -> ToolResult:
        """输出进入 LLM/历史/前端前的统一兜底：截断 + secret 回扫脱敏。"""
        out = result.output or ""
        limit = self.config.permissions.max_output_bytes
        data = out.encode("utf-8", "ignore")
        if len(data) > limit:
            out = data[:limit].decode("utf-8", "ignore") + "\n…[输出已截断]"
        if self.config.permissions.scrub_secrets:
            out = str(redact(out))
        return ToolResult(output=out, diff=result.diff, error=result.error)

    async def _request_approval(
        self, session: Session, tool_id: str, name: str, args: Dict[str, Any], reason: str
    ) -> str:
        approval_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        session.pending_approvals[approval_id] = ApprovalItem(
            approval_id=approval_id, tool=name, args=args, message=reason, future=future
        )
        await self._emit(
            session, E.approval_request(approval_id, name, args, reason)
        )
        decision = await future
        session.pending_approvals.pop(approval_id, None)
        if self._audit is not None:
            self._audit.record("approval", tool=name, decision=decision)
        return decision

    async def _request_answer(self, session: Session, args: Dict[str, Any]) -> str:
        question = str(args.get("question", "")).strip() or "请补充信息"
        options = self._normalize_options(args.get("options"))
        multi = bool(args.get("multi", False))
        question_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        session.pending_questions[question_id] = QuestionItem(
            question_id=question_id, question=question, future=future,
            options=options, multi=multi,
        )
        await self._emit(session, E.ask_user(question_id, question, options, multi))
        answer = await future
        session.pending_questions.pop(question_id, None)
        return str(answer)

    @staticmethod
    def _normalize_options(raw: Any) -> List[Dict[str, Any]]:
        """把模型给的 options 归一化为 [{label, description?, recommended?}]。"""
        if not isinstance(raw, (list, tuple)):
            return []
        out: List[Dict[str, Any]] = []
        for o in raw:
            if isinstance(o, dict) and o.get("label"):
                out.append(
                    {
                        "label": str(o["label"]).strip(),
                        "description": str(o.get("description", "")).strip() or None,
                        "recommended": bool(o.get("recommended", False)),
                    }
                )
            elif isinstance(o, str) and o.strip():
                out.append({"label": o.strip(), "description": None, "recommended": False})
        return out

    async def _request_safety(self, session: Session, verdicts: Any) -> str:
        safety_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        reasons = [v.reason for v in verdicts]
        severity = (
            SEVERITY_HIGH if any(v.severity == SEVERITY_HIGH for v in verdicts)
            else SEVERITY_MEDIUM
        )
        session.pending_safety[safety_id] = SafetyItem(
            safety_id=safety_id, reasons=reasons, severity=severity, future=future
        )
        await self._emit(session, E.safety(safety_id, reasons, severity))
        decision = await future
        session.pending_safety.pop(safety_id, None)
        return str(decision)

    def _parse_args(self, raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}

    async def _build_messages(self, state: RunState, session: Session) -> List[Message]:
        if self._memory is not None:
            prompt, msgs = await self._memory.build_context(
                session, self.config.system_prompt or "", self._skills_section,
                model=self.config.resolve_model(),
            )
        else:
            prompt = self.config.system_prompt or ""
            if self._skills_section:
                prompt = (prompt + "\n" + self._skills_section) if prompt else self._skills_section
            msgs = list(session.messages)

        if state.intent_section:
            prompt = (prompt + "\n" + state.intent_section) if prompt else state.intent_section

        if state.skill_content:
            prompt = (prompt + "\n\n## Skill 指令\n" + state.skill_content) if prompt else state.skill_content

        prompt = (prompt + "\n" + _ASK_USER_GUIDANCE) if prompt else _ASK_USER_GUIDANCE

        out: List[Message] = []
        if prompt:
            out.append(Message(role="system", content=prompt))
        out.extend(msgs)
        return out

    async def _recognize_intent(self, state: RunState, user_content: str) -> None:
        session = state.session
        if self._intent is None or not self.config.intent.enabled:
            return
        try:
            with tracing.span("intent", logger=_logger):
                plan = await self._intent.recognize(session, user_content, self.tools.meta())
        except Exception:
            return
        state.active_tools = plan.tool_names
        state.intent_section = self._intent_system_section(plan)
        state.last_intent_category = plan.category
        _logger.info(
            "intent.recognized",
            extra={"category": plan.category, "confidence": plan.confidence},
        )
        await self._emit(session, E.intent(plan.to_dict()))

    async def _dispatch_skill(self, state: RunState, user_content: str) -> None:
        """确定性 skill 触发：命中 trigger 关键词时自动把该 skill 全文注入上下文。"""
        if self._skills_registry is None:
            return
        skill = self._skills_registry.match(user_content)
        if skill is None:
            return
        state.skill_content = skill.content
        await self._emit(
            state.session, E.progress("skill", "已匹配 skill：{}".format(skill.name))
        )

    def _intent_system_section(self, plan: Any) -> str:
        labels = {
            "code_edit": "修改/编写代码",
            "code_read": "阅读/解释代码",
            "explore": "搜索/浏览代码库",
            "execute": "执行命令/构建/测试",
            "question": "回答/解释概念",
            "plan": "规划/设计（只分析，不修改文件）",
            "compose": "内容创作/写作（写文章、小说、文案等）",
            "chat": "闲聊",
        }
        label = labels.get(plan.category)
        if not label:
            return ""
        return "\n## 意图\n当前用户意图：{}。请据此选用合适工具并聚焦回复。".format(label)
