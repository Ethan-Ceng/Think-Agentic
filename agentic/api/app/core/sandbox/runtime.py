from __future__ import annotations

import asyncio
import logging
from typing import BinaryIO, Callable, Optional, Type

from app.core.browser.base import Browser
from app.core.browser.lazy import LazyBrowser
from app.core.entities.tool_result import ToolResult
from app.core.sandbox.base import Sandbox
from app.repositories.uow import IUnitOfWork

logger = logging.getLogger(__name__)


class SandboxNotActivatedError(RuntimeError):
    """Raised when synchronous Sandbox metadata is read before activation."""


class LazySandboxRuntime:
    """Own one lazily resolved Sandbox and Browser for an Agent Session."""

    def __init__(
        self,
        *,
        session_id: str,
        sandbox_id: Optional[str],
        sandbox_cls: Type[Sandbox],
        uow_factory: Callable[[], IUnitOfWork],
    ) -> None:
        self._session_id = session_id
        self._sandbox_id = sandbox_id
        self._sandbox_cls = sandbox_cls
        self._uow_factory = uow_factory
        self._sandbox: Optional[Sandbox] = None
        self._browser: Optional[Browser] = None
        self._sandbox_lock = asyncio.Lock()
        self._browser_lock = asyncio.Lock()
        self.sandbox = LazySandboxProxy(self)
        self.browser = LazyBrowser(self)

    @property
    def is_activated(self) -> bool:
        return self._sandbox is not None

    @property
    def active_sandbox(self) -> Optional[Sandbox]:
        """Return the cached instance without activating or restoring it."""
        return self._sandbox

    async def get_sandbox(self) -> Sandbox:
        sandbox = self._sandbox
        if sandbox is not None:
            self._log_reuse(sandbox, source="memory")
            return sandbox

        async with self._sandbox_lock:
            sandbox = self._sandbox
            if sandbox is not None:
                self._log_reuse(sandbox, source="memory_after_lock")
                return sandbox

            expected_sandbox_id = self._sandbox_id
            if expected_sandbox_id:
                sandbox = await self._try_restore(expected_sandbox_id)
                if sandbox is not None:
                    self._sandbox = sandbox
                    self._log_reuse(sandbox, source="persisted_handle")
                    return sandbox

            return await self._create_and_claim(expected_sandbox_id)

    async def get_browser(self) -> Browser:
        browser = self._browser
        if browser is not None:
            return browser

        sandbox = await self.get_sandbox()
        async with self._browser_lock:
            browser = self._browser
            if browser is not None:
                return browser
            try:
                browser = await sandbox.get_browser()
                if browser is None:
                    raise RuntimeError(
                        f"获取沙箱[{sandbox.id}]中的浏览器实例失败"
                    )
            except BaseException as exc:
                self._log_failed("get_browser", exc)
                raise
            self._browser = browser
            return browser

    async def destroy(self) -> bool:
        """Destroy only an instance that was actually activated."""
        async with self._sandbox_lock:
            sandbox = self._sandbox
            if sandbox is None:
                return True
            self._sandbox = None
            self._browser = None
            try:
                return await sandbox.destroy()
            except BaseException as exc:
                self._log_failed("destroy", exc)
                raise

    async def _try_restore(self, sandbox_id: str) -> Optional[Sandbox]:
        try:
            return await self._sandbox_cls.get(sandbox_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log_failed("restore", exc, sandbox_id=sandbox_id)
            return None

    async def _create_and_claim(
        self,
        expected_sandbox_id: Optional[str],
    ) -> Sandbox:
        created: Optional[Sandbox] = None
        candidate_owned = False
        try:
            created = await self._sandbox_cls.create()
            candidate_owned = True
            winner_id = await self._claim_sandbox_id(
                created.id,
                expected_sandbox_id=expected_sandbox_id,
            )
            if winner_id != created.id:
                await self._destroy_unclaimed(created)
                candidate_owned = False
                winner = await self._sandbox_cls.get(winner_id)
                if winner is None:
                    self._sandbox_id = winner_id
                    raise RuntimeError(
                        f"并发创建的 Sandbox [{winner_id}] 无法恢复"
                    )
                self._sandbox_id = winner_id
                self._sandbox = winner
                self._log_reuse(winner, source="concurrent_winner")
                return winner

            self._sandbox_id = created.id
            self._sandbox = created
            candidate_owned = False
            logger.info(
                "sandbox_lazy_create",
                extra={
                    "session_id": self._session_id,
                    "sandbox_id": created.id,
                },
            )
            return created
        except BaseException as exc:
            if created is not None and candidate_owned:
                await self._destroy_unclaimed(created)
            self._log_failed("create", exc)
            raise

    async def _claim_sandbox_id(
        self,
        candidate_id: str,
        *,
        expected_sandbox_id: Optional[str],
    ) -> str:
        uow = self._uow_factory()
        async with uow:
            return await uow.session.claim_sandbox_id(
                self._session_id,
                candidate_id,
                expected_sandbox_id=expected_sandbox_id,
            )

    async def _destroy_unclaimed(self, sandbox: Sandbox) -> None:
        try:
            await sandbox.destroy()
        except BaseException as exc:
            self._log_failed(
                "destroy_unclaimed",
                exc,
                sandbox_id=sandbox.id,
            )

    def _log_reuse(self, sandbox: Sandbox, *, source: str) -> None:
        logger.info(
            "sandbox_lazy_reuse",
            extra={
                "session_id": self._session_id,
                "sandbox_id": sandbox.id,
                "source": source,
            },
        )

    def _log_failed(
        self,
        operation: str,
        exc: BaseException,
        *,
        sandbox_id: Optional[str] = None,
    ) -> None:
        logger.warning(
            "sandbox_lazy_failed",
            extra={
                "session_id": self._session_id,
                "sandbox_id": sandbox_id or self._sandbox_id,
                "operation": operation,
                "error_type": type(exc).__name__,
            },
        )


class LazySandboxProxy:
    """Sandbox protocol proxy whose async methods activate on demand."""

    def __init__(self, runtime: LazySandboxRuntime) -> None:
        self._runtime = runtime

    def _active(self) -> Sandbox:
        sandbox = self._runtime.active_sandbox
        if sandbox is None:
            raise SandboxNotActivatedError(
                "Sandbox 尚未激活；请先调用异步 Sandbox 能力"
            )
        return sandbox

    @property
    def id(self) -> str:
        return self._active().id

    @property
    def cdp_url(self) -> str:
        return self._active().cdp_url

    @property
    def vnc_url(self) -> str:
        return self._active().vnc_url

    async def _sandbox(self) -> Sandbox:
        return await self._runtime.get_sandbox()

    async def exec_command(
        self,
        session_id: str,
        exec_dir: str,
        command: str,
    ) -> ToolResult:
        return await (await self._sandbox()).exec_command(
            session_id,
            exec_dir,
            command,
        )

    async def read_shell_output(
        self,
        session_id: str,
        console: bool = False,
    ) -> ToolResult:
        return await (await self._sandbox()).read_shell_output(
            session_id,
            console,
        )

    async def wait_process(
        self,
        session_id: str,
        seconds: Optional[int] = None,
    ) -> ToolResult:
        return await (await self._sandbox()).wait_process(session_id, seconds)

    async def write_shell_input(
        self,
        session_id: str,
        input_text: str,
        press_enter: bool = True,
    ) -> ToolResult:
        return await (await self._sandbox()).write_shell_input(
            session_id,
            input_text,
            press_enter,
        )

    async def kill_process(self, session_id: str) -> ToolResult:
        return await (await self._sandbox()).kill_process(session_id)

    async def write_file(
        self,
        filepath: str,
        content: str,
        append: bool = False,
        leading_newline: bool = False,
        trailing_newline: bool = False,
        sudo: bool = False,
    ) -> ToolResult:
        return await (await self._sandbox()).write_file(
            filepath,
            content,
            append=append,
            leading_newline=leading_newline,
            trailing_newline=trailing_newline,
            sudo=sudo,
        )

    async def read_file(
        self,
        filepath: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        sudo: bool = False,
        max_length: int = 10000,
    ) -> ToolResult:
        return await (await self._sandbox()).read_file(
            filepath,
            start_line=start_line,
            end_line=end_line,
            sudo=sudo,
            max_length=max_length,
        )

    async def check_file_exists(self, filepath: str) -> ToolResult:
        return await (await self._sandbox()).check_file_exists(filepath)

    async def delete_file(self, filepath: str) -> ToolResult:
        return await (await self._sandbox()).delete_file(filepath)

    async def list_files(self, dir_path: str) -> ToolResult:
        return await (await self._sandbox()).list_files(dir_path)

    async def replace_in_file(
        self,
        filepath: str,
        old_str: str,
        new_str: str,
        sudo: bool = False,
    ) -> ToolResult:
        return await (await self._sandbox()).replace_in_file(
            filepath,
            old_str,
            new_str,
            sudo=sudo,
        )

    async def search_in_file(
        self,
        filepath: str,
        regex: str,
        sudo: bool = False,
    ) -> ToolResult:
        return await (await self._sandbox()).search_in_file(
            filepath,
            regex,
            sudo=sudo,
        )

    async def find_files(
        self,
        dir_path: str,
        glob_pattern: str,
    ) -> ToolResult:
        return await (await self._sandbox()).find_files(
            dir_path,
            glob_pattern,
        )

    async def upload_file(
        self,
        file_data: BinaryIO,
        filepath: str,
        filename: Optional[str] = None,
    ) -> ToolResult:
        return await (await self._sandbox()).upload_file(
            file_data,
            filepath,
            filename,
        )

    async def download_file(self, filepath: str) -> BinaryIO:
        return await (await self._sandbox()).download_file(filepath)

    async def ensure_sandbox(self) -> None:
        await (await self._sandbox()).ensure_sandbox()

    async def destroy(self) -> bool:
        return await self._runtime.destroy()

    async def get_browser(self) -> Browser:
        return await self._runtime.get_browser()

