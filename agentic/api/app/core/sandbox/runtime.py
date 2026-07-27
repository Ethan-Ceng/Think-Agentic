from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import PurePosixPath
from time import perf_counter
from typing import Awaitable, BinaryIO, Callable, Optional, Type

from app.core.browser.base import Browser
from app.core.browser.lazy import LazyBrowser
from app.core.entities.file import File
from app.core.entities.tool_result import ToolResult
from app.core.sandbox.base import Sandbox
from app.extensions.file_storage import FileStorage
from app.repositories.uow import IUnitOfWork

logger = logging.getLogger(__name__)


class SandboxNotActivatedError(RuntimeError):
    """Raised when synchronous Sandbox metadata is read before activation."""


@dataclass(frozen=True)
class SandboxAttachment:
    file: File
    sandbox_path: str

    @property
    def prompt_text(self) -> str:
        media_type = self.file.mime_type or "application/octet-stream"
        display_name = PurePosixPath(self.sandbox_path).name
        return (
            f"{display_name} "
            f"[file_id={self.file.id}, mime={media_type}, size={self.file.size}; "
            f"sandbox_path_after_activation={self.sandbox_path}]"
        )


@dataclass(frozen=True)
class SandboxActivation:
    activation_reason: str
    first_capability: str
    operation_counts: dict[str, int]
    startup_ms: int
    attachment_sync_bytes: int
    materialized_files: tuple[File, ...] = ()


@dataclass(frozen=True)
class MaterializationResult:
    files: tuple[File, ...] = ()
    upload_count: int = 0
    uploaded_bytes: int = 0


class SandboxAttachmentMaterializer:
    """Download authorized managed files and upload each once per Sandbox."""

    UPLOAD_ROOT = "/home/ubuntu/upload"

    def __init__(
        self,
        *,
        file_storage: FileStorage,
        user_id: str,
    ) -> None:
        self._file_storage = file_storage
        self._user_id = user_id
        self._materialized: dict[str, File] = {}
        self._paths_by_file_id: dict[str, str] = {}
        self._path_owners: dict[str, str] = {}

    def prepare_manifest(
        self,
        attachments: list[File],
    ) -> list[SandboxAttachment]:
        entries: list[SandboxAttachment] = []
        seen: set[str] = set()
        for attachment in attachments:
            if not attachment.id or attachment.id in seen:
                continue
            seen.add(attachment.id)
            sandbox_path = self._paths_by_file_id.get(attachment.id)
            if sandbox_path is None:
                sandbox_path = self._allocate_path(attachment)
                self._paths_by_file_id[attachment.id] = sandbox_path
                self._path_owners[sandbox_path] = attachment.id
            entries.append(
                SandboxAttachment(
                    file=attachment,
                    sandbox_path=sandbox_path,
                )
            )
        return entries

    async def materialize(
        self,
        sandbox: Sandbox,
        entries: list[SandboxAttachment],
    ) -> MaterializationResult:
        files: list[File] = []
        uploaded_bytes = 0
        for entry in entries:
            if entry.file.id in self._materialized:
                continue

            file_data, authoritative = await self._file_storage.download_file(
                entry.file.id,
                user_id=self._user_id,
            )
            upload_name = PurePosixPath(entry.sandbox_path).name
            try:
                if authoritative.id != entry.file.id:
                    raise RuntimeError(
                        f"附件[{entry.file.id}]下载结果标识不一致"
                    )
                result = await sandbox.upload_file(
                    file_data=file_data,
                    filepath=entry.sandbox_path,
                    filename=upload_name,
                )
            finally:
                close = getattr(file_data, "close", None)
                if callable(close):
                    close()

            if not result.success:
                raise RuntimeError(
                    result.message
                    or f"附件[{authoritative.id}]同步到 Sandbox 失败"
                )

            materialized = authoritative.model_copy(
                update={"filepath": entry.sandbox_path}
            )
            self._materialized[entry.file.id] = materialized
            files.append(materialized)
            uploaded_bytes += max(0, authoritative.size)

        return MaterializationResult(
            files=tuple(files),
            upload_count=len(files),
            uploaded_bytes=uploaded_bytes,
        )

    def reset(self) -> None:
        self._materialized.clear()

    def _allocate_path(self, file: File) -> str:
        filename = self._safe_filename(file.filename, file.id)
        candidate = f"{self.UPLOAD_ROOT}/{filename}"
        if candidate not in self._path_owners:
            return candidate

        path = PurePosixPath(filename)
        stem = path.stem or "attachment"
        suffix = path.suffix
        short_id = (file.id or "file")[:8]
        candidate = f"{self.UPLOAD_ROOT}/{stem}-{short_id}{suffix}"
        index = 2
        while (
            candidate in self._path_owners
            and self._path_owners[candidate] != file.id
        ):
            candidate = (
                f"{self.UPLOAD_ROOT}/{stem}-{short_id}-{index}{suffix}"
            )
            index += 1
        return candidate

    @staticmethod
    def _safe_filename(filename: str, file_id: str) -> str:
        normalized = (filename or "").replace("\\", "/")
        basename = PurePosixPath(normalized).name
        basename = "".join(
            character
            for character in basename
            if character >= " " and character != "\x7f"
        ).strip()
        if basename in {"", ".", ".."}:
            basename = f"attachment-{(file_id or 'file')[:8]}"
        if len(basename) > 180:
            path = PurePosixPath(basename)
            suffix = path.suffix[:20]
            basename = f"{path.stem[: 180 - len(suffix)]}{suffix}"
        return basename


ActivationObserver = Callable[[SandboxActivation], Awaitable[None]]


class LazySandboxRuntime:
    """Own one lazily resolved Sandbox and Browser for an Agent Session."""

    def __init__(
        self,
        *,
        session_id: str,
        sandbox_id: Optional[str],
        sandbox_cls: Type[Sandbox],
        uow_factory: Callable[[], IUnitOfWork],
        attachment_materializer: Optional[SandboxAttachmentMaterializer] = None,
        activation_observer: Optional[ActivationObserver] = None,
    ) -> None:
        self._session_id = session_id
        self._sandbox_id = sandbox_id
        self._sandbox_cls = sandbox_cls
        self._uow_factory = uow_factory
        self._sandbox: Optional[Sandbox] = None
        self._browser: Optional[Browser] = None
        self._sandbox_ready = False
        self._sandbox_lock = asyncio.Lock()
        self._browser_lock = asyncio.Lock()
        self._attachment_materializer = attachment_materializer
        self._activation_observer = activation_observer
        self._attachment_manifest: list[SandboxAttachment] = []
        self._manifest_version = 0
        self._prepared_manifest_version = -1
        self._notified_manifest_version = -1
        self._activation_started: Optional[float] = None
        self._activation_counts = self._empty_operation_counts()
        self._last_materialized_files: tuple[File, ...] = ()
        self._attachment_sync_bytes = 0
        self.sandbox = LazySandboxProxy(self)
        self.browser = LazyBrowser(self)

    @property
    def is_activated(self) -> bool:
        return self._sandbox is not None

    @property
    def active_sandbox(self) -> Optional[Sandbox]:
        """Return the cached instance without activating or restoring it."""
        return self._sandbox

    def set_activation_observer(
        self,
        observer: Optional[ActivationObserver],
    ) -> None:
        self._activation_observer = observer

    def set_attachment_manifest(
        self,
        attachments: list[File],
    ) -> list[SandboxAttachment]:
        if self._attachment_materializer is None:
            self._attachment_manifest = [
                SandboxAttachment(
                    file=attachment,
                    sandbox_path=(
                        f"/home/ubuntu/upload/"
                        f"{SandboxAttachmentMaterializer._safe_filename(attachment.filename, attachment.id)}"
                    ),
                )
                for attachment in attachments
                if attachment.id
            ]
        else:
            self._attachment_manifest = (
                self._attachment_materializer.prepare_manifest(attachments)
            )
        self._manifest_version += 1
        self._prepared_manifest_version = -1
        self._notified_manifest_version = -1
        self._activation_started = None
        self._activation_counts = self._empty_operation_counts()
        self._last_materialized_files = ()
        self._attachment_sync_bytes = 0
        return list(self._attachment_manifest)

    async def get_sandbox(
        self,
        *,
        capability: str = "sandbox",
        notify: bool = True,
        materialize: bool = True,
    ) -> Sandbox:
        async with self._sandbox_lock:
            if self._activation_started is None:
                self._activation_started = perf_counter()
            sandbox = self._sandbox
            if sandbox is not None:
                self._log_reuse(sandbox, source="memory")
            else:
                expected_sandbox_id = self._sandbox_id
                if expected_sandbox_id:
                    self._activation_counts["get"] += 1
                    sandbox = await self._try_restore(expected_sandbox_id)
                    if sandbox is not None:
                        self._sandbox = sandbox
                        self._sandbox_ready = False
                        self._log_reuse(
                            sandbox,
                            source="persisted_handle",
                        )

                if sandbox is None:
                    sandbox = await self._create_and_claim(
                        expected_sandbox_id
                    )

            if not self._sandbox_ready:
                self._activation_counts["ensure"] += 1
                ensure_started = perf_counter()
                try:
                    await sandbox.ensure_sandbox()
                except BaseException as exc:
                    self._log_failed("ensure", exc, sandbox_id=sandbox.id)
                    raise
                finally:
                    if self._activation_started is None:
                        self._activation_started = ensure_started
                self._sandbox_ready = True

            if (
                materialize
                and self._prepared_manifest_version
                != self._manifest_version
            ):
                materialized = await self._materialize_attachments(sandbox)
                self._last_materialized_files = materialized.files
                self._activation_counts["upload_file"] += (
                    materialized.upload_count
                )
                self._attachment_sync_bytes += materialized.uploaded_bytes
                self._prepared_manifest_version = self._manifest_version

            if notify:
                await self._notify_activation(capability)
            return sandbox

    async def get_browser(self) -> Browser:
        sandbox = await self.get_sandbox(
            capability="browser",
            notify=False,
        )
        async with self._browser_lock:
            browser = self._browser
            if browser is None:
                self._activation_counts["get_browser"] += 1
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
        await self._notify_activation("browser")
        return browser

    async def destroy(self) -> bool:
        """Destroy only an instance that was actually activated."""
        async with self._sandbox_lock:
            sandbox = self._sandbox
            if sandbox is None:
                return True
            self._sandbox = None
            self._browser = None
            self._sandbox_ready = False
            self._prepared_manifest_version = -1
            if self._attachment_materializer is not None:
                self._attachment_materializer.reset()
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
            self._activation_counts["create"] += 1
            created = await self._sandbox_cls.create()
            candidate_owned = True
            winner_id = await self._claim_sandbox_id(
                created.id,
                expected_sandbox_id=expected_sandbox_id,
            )
            if winner_id != created.id:
                await self._destroy_unclaimed(created)
                candidate_owned = False
                self._activation_counts["get"] += 1
                winner = await self._sandbox_cls.get(winner_id)
                if winner is None:
                    self._sandbox_id = winner_id
                    raise RuntimeError(
                        f"并发创建的 Sandbox [{winner_id}] 无法恢复"
                    )
                self._sandbox_id = winner_id
                self._sandbox = winner
                self._sandbox_ready = False
                self._log_reuse(winner, source="concurrent_winner")
                return winner

            self._sandbox_id = created.id
            self._sandbox = created
            self._sandbox_ready = False
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

    async def _materialize_attachments(
        self,
        sandbox: Sandbox,
    ) -> MaterializationResult:
        if (
            self._attachment_materializer is None
            or not self._attachment_manifest
        ):
            return MaterializationResult()
        try:
            return await self._attachment_materializer.materialize(
                sandbox,
                self._attachment_manifest,
            )
        except BaseException as exc:
            self._log_failed(
                "materialize_attachments",
                exc,
                sandbox_id=sandbox.id,
            )
            raise

    async def _notify_activation(self, capability: str) -> None:
        if self._notified_manifest_version == self._manifest_version:
            return
        observer = self._activation_observer
        if observer is None:
            return

        started = self._activation_started or perf_counter()
        activation = SandboxActivation(
            activation_reason="tool_invocation",
            first_capability=capability,
            operation_counts=dict(self._activation_counts),
            startup_ms=max(0, int((perf_counter() - started) * 1000)),
            attachment_sync_bytes=self._attachment_sync_bytes,
            materialized_files=self._last_materialized_files,
        )
        self._notified_manifest_version = self._manifest_version
        try:
            await observer(activation)
        except Exception as exc:
            self._log_failed("activation_observer", exc)

    @staticmethod
    def _empty_operation_counts() -> dict[str, int]:
        return {
            "create": 0,
            "get": 0,
            "ensure": 0,
            "get_browser": 0,
            "upload_file": 0,
        }

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
        await self._runtime.get_sandbox()

    async def destroy(self) -> bool:
        return await self._runtime.destroy()

    async def get_browser(self) -> Browser:
        return await self._runtime.get_browser()
