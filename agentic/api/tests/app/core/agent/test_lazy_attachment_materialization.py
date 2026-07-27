from __future__ import annotations

import asyncio
import io

import pytest

from app.core.entities.file import File
from app.core.entities.tool_result import ToolResult
from app.core.sandbox.runtime import (
    LazySandboxRuntime,
    SandboxActivation,
    SandboxAttachmentMaterializer,
)


class RecordingSessionRepository:
    def __init__(self) -> None:
        self.sandbox_id: str | None = None

    async def claim_sandbox_id(
        self,
        session_id: str,
        candidate_id: str,
        *,
        expected_sandbox_id: str | None,
    ) -> str:
        assert session_id == "session-1"
        assert self.sandbox_id == expected_sandbox_id
        self.sandbox_id = candidate_id
        return candidate_id


class FakeUow:
    def __init__(self, repository: RecordingSessionRepository) -> None:
        self.session = repository

    async def __aenter__(self) -> "FakeUow":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class RecordingFileStorage:
    def __init__(self, payloads: dict[str, tuple[bytes, File]]) -> None:
        self.payloads = payloads
        self.downloads: list[tuple[str, str | None]] = []

    async def download_file(self, file_id: str, user_id: str | None = None):
        self.downloads.append((file_id, user_id))
        payload, file = self.payloads[file_id]
        return io.BytesIO(payload), file


class RecordingSandbox:
    def __init__(self, sandbox_id: str) -> None:
        self.id = sandbox_id
        self.cdp_url = f"http://{sandbox_id}/cdp"
        self.vnc_url = f"ws://{sandbox_id}/vnc"
        self.calls: list[str] = []
        self.uploads: list[tuple[str, str, bytes]] = []
        self.fail_next_upload = False
        self.browser_calls = 0

    async def ensure_sandbox(self) -> None:
        self.calls.append("ensure")

    async def upload_file(self, file_data, filepath: str, filename: str):
        self.calls.append(f"upload:{filename}")
        payload = file_data.read()
        if self.fail_next_upload:
            self.fail_next_upload = False
            return ToolResult(success=False, message="upload failed")
        self.uploads.append((filepath, filename, payload))
        return ToolResult(success=True)

    async def read_file(self, filepath: str, **kwargs) -> ToolResult:
        self.calls.append(f"read:{filepath}")
        return ToolResult(success=True, data={"content": "ok"})

    async def get_browser(self):
        self.browser_calls += 1
        sandbox = self

        class Browser:
            async def navigate(self, url: str) -> ToolResult:
                sandbox.calls.append(f"navigate:{url}")
                return ToolResult(success=True)

        return Browser()

    async def destroy(self) -> bool:
        return True


class RecordingSandboxClass:
    create_calls = 0
    instance: RecordingSandbox | None = None

    @classmethod
    def reset(cls) -> None:
        cls.create_calls = 0
        cls.instance = None

    @classmethod
    async def create(cls) -> RecordingSandbox:
        cls.create_calls += 1
        cls.instance = RecordingSandbox("sandbox-1")
        return cls.instance

    @classmethod
    async def get(cls, sandbox_id: str):
        return cls.instance if cls.instance and cls.instance.id == sandbox_id else None


def _file(file_id: str, filename: str, payload: bytes) -> tuple[bytes, File]:
    return payload, File(
        id=file_id,
        user_id="user-1",
        filename=filename,
        size=len(payload),
        mime_type="text/plain",
    )


def make_runtime(
    payloads: dict[str, tuple[bytes, File]],
) -> tuple[LazySandboxRuntime, RecordingFileStorage, list[SandboxActivation]]:
    RecordingSandboxClass.reset()
    repository = RecordingSessionRepository()
    storage = RecordingFileStorage(payloads)
    activations: list[SandboxActivation] = []

    async def observe(activation: SandboxActivation) -> None:
        activations.append(activation)

    runtime = LazySandboxRuntime(
        session_id="session-1",
        sandbox_id=None,
        sandbox_cls=RecordingSandboxClass,
        uow_factory=lambda: FakeUow(repository),
        attachment_materializer=SandboxAttachmentMaterializer(
            file_storage=storage,
            user_id="user-1",
        ),
        activation_observer=observe,
    )
    return runtime, storage, activations


def test_manifest_does_not_download_or_start_sandbox() -> None:
    payloads = {"file-1": _file("file-1", "contract.txt", b"contract")}
    runtime, storage, activations = make_runtime(payloads)

    entries = runtime.set_attachment_manifest([payloads["file-1"][1]])

    assert RecordingSandboxClass.create_calls == 0
    assert storage.downloads == []
    assert activations == []
    assert entries[0].sandbox_path == "/home/ubuntu/upload/contract.txt"
    assert "sandbox_path_after_activation" in entries[0].prompt_text


def test_first_sandbox_method_ensures_then_materializes_once() -> None:
    async def scenario() -> None:
        payloads = {"file-1": _file("file-1", "contract.txt", b"contract")}
        runtime, storage, activations = make_runtime(payloads)
        entry = runtime.set_attachment_manifest([payloads["file-1"][1]])[0]

        first = await runtime.sandbox.read_file(entry.sandbox_path)
        second = await runtime.sandbox.read_file(entry.sandbox_path)

        sandbox = RecordingSandboxClass.instance
        assert first.success and second.success
        assert sandbox is not None
        assert sandbox.calls == [
            "ensure",
            "upload:contract.txt",
            f"read:{entry.sandbox_path}",
            f"read:{entry.sandbox_path}",
        ]
        assert storage.downloads == [("file-1", "user-1")]
        assert sandbox.uploads == [
            (entry.sandbox_path, "contract.txt", b"contract")
        ]
        assert len(activations) == 1
        assert activations[0].first_capability == "sandbox"
        assert activations[0].operation_counts == {
            "create": 1,
            "get": 0,
            "ensure": 1,
            "get_browser": 0,
            "upload_file": 1,
        }
        assert activations[0].attachment_sync_bytes == len(b"contract")

    asyncio.run(scenario())


def test_next_run_only_uploads_new_attachment() -> None:
    async def scenario() -> None:
        payloads = {
            "file-1": _file("file-1", "first.txt", b"first"),
            "file-2": _file("file-2", "second.txt", b"second"),
        }
        runtime, storage, activations = make_runtime(payloads)
        first_entry = runtime.set_attachment_manifest([payloads["file-1"][1]])[0]
        await runtime.sandbox.read_file(first_entry.sandbox_path)

        entries = runtime.set_attachment_manifest(
            [payloads["file-1"][1], payloads["file-2"][1]]
        )
        await runtime.sandbox.read_file(entries[1].sandbox_path)

        assert RecordingSandboxClass.create_calls == 1
        assert storage.downloads == [
            ("file-1", "user-1"),
            ("file-2", "user-1"),
        ]
        assert len(activations) == 2
        assert activations[1].operation_counts["create"] == 0
        assert activations[1].operation_counts["upload_file"] == 1
        assert activations[1].materialized_files[0].id == "file-2"

    asyncio.run(scenario())


def test_first_browser_method_materializes_before_browser_navigation() -> None:
    async def scenario() -> None:
        payloads = {"file-1": _file("file-1", "browser.txt", b"browser")}
        runtime, storage, activations = make_runtime(payloads)
        runtime.set_attachment_manifest([payloads["file-1"][1]])

        result = await runtime.browser.navigate("https://example.com")

        sandbox = RecordingSandboxClass.instance
        assert result.success
        assert sandbox is not None
        assert sandbox.calls == [
            "ensure",
            "upload:browser.txt",
            "navigate:https://example.com",
        ]
        assert sandbox.browser_calls == 1
        assert storage.downloads == [("file-1", "user-1")]
        assert activations[0].first_capability == "browser"
        assert activations[0].operation_counts["get_browser"] == 1

    asyncio.run(scenario())


def test_unsafe_and_duplicate_filenames_receive_safe_stable_paths() -> None:
    payloads = {
        "file-1": _file("file-1", "../../report.txt", b"one"),
        "file-2": _file("file-2", r"..\\..\\report.txt", b"two"),
    }
    runtime, _, _ = make_runtime(payloads)

    first, second = runtime.set_attachment_manifest(
        [payloads["file-1"][1], payloads["file-2"][1]]
    )

    assert first.sandbox_path == "/home/ubuntu/upload/report.txt"
    assert second.sandbox_path.startswith("/home/ubuntu/upload/report-file-2")
    assert ".." not in first.sandbox_path
    assert ".." not in second.sandbox_path
    assert "../" not in first.prompt_text
    assert "..\\" not in second.prompt_text


def test_failed_upload_is_not_cached_and_can_retry() -> None:
    async def scenario() -> None:
        payloads = {"file-1": _file("file-1", "retry.txt", b"retry")}
        runtime, storage, activations = make_runtime(payloads)
        entry = runtime.set_attachment_manifest([payloads["file-1"][1]])[0]
        sandbox = await runtime.get_sandbox(notify=False, materialize=False)
        sandbox.fail_next_upload = True

        with pytest.raises(RuntimeError, match="upload failed"):
            await runtime.sandbox.read_file(entry.sandbox_path)

        assert activations == []
        assert await runtime.sandbox.read_file(entry.sandbox_path)
        assert storage.downloads == [
            ("file-1", "user-1"),
            ("file-1", "user-1"),
        ]

    asyncio.run(scenario())
