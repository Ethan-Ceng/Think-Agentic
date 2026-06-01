import uuid
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_current_account, get_db_session, get_upload_file_service
from app.app_factory import create_app
from app.core.config import Settings
from app.models.account import Account
from app.schemas.upload_file import UploadFileResponse


def test_upload_file_response_keeps_legacy_payload_shape() -> None:
    upload_file = SimpleNamespace(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        name="doc.txt",
        key="2024/01/01/doc.txt",
        size=5,
        extension="txt",
        mime_type="text/plain",
        created_at=datetime(2024, 1, 1),
    )

    response = UploadFileResponse.from_upload_file(upload_file)

    assert response.name == "doc.txt"
    assert response.extension == "txt"


def test_upload_file_route_keeps_legacy_payload_shape() -> None:
    upload_file = SimpleNamespace(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        name="doc.txt",
        key="2024/01/01/doc.txt",
        size=5,
        extension="txt",
        mime_type="text/plain",
        created_at=datetime(2024, 1, 1),
    )

    class FakeUploadFileService:
        def upload_file(self, session, file, only_image, current_user):  # noqa: ANN001
            return upload_file

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: Account(
        id=uuid.uuid4(),
        name="tester",
        email="tester@example.test",
    )
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_upload_file_service] = lambda: FakeUploadFileService()

    with TestClient(app) as client:
        response = client.post("/upload-files", files={"file": ("doc.txt", b"hello", "text/plain")})

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert response.json()["data"]["name"] == "doc.txt"


def test_get_uploaded_file_serves_local_storage(tmp_path) -> None:
    storage_file = tmp_path / "2026" / "06" / "01" / "doc.txt"
    storage_file.parent.mkdir(parents=True)
    storage_file.write_text("hello", encoding="utf-8")

    app = create_app(Settings(app_env="test", debug=False, local_storage_root=str(tmp_path)))
    with TestClient(app) as client:
        response = client.get("/upload-files/2026/06/01/doc.txt")

    assert response.status_code == 200
    assert response.text == "hello"
