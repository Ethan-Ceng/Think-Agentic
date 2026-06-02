import uuid

from fastapi.testclient import TestClient

from app.api.deps import get_current_account, get_db_session, get_file_service
from app.app_factory import create_app
from app.core.config import Settings
from app.models.account import Account


def test_list_files_treats_undefined_parent_id_as_root() -> None:
    account = Account(id=uuid.uuid4(), name="tester", email="tester@example.test")

    class FakeFileService:
        def list_files_with_page(
            self,
            session,
            current_user,
            *,
            parent_id,
            search_word,
            file_kind,
            source_filter,
            current_page,
            page_size,
        ):  # noqa: ANN001
            assert parent_id is None
            assert search_word == ""
            assert file_kind == "all"
            assert source_filter == "all"
            assert current_page == 1
            assert page_size == 20
            return [], 0, 0

        def to_response(self, session, file):  # noqa: ANN001
            return {}

    app = create_app(Settings(app_env="test", debug=False))
    app.dependency_overrides[get_current_account] = lambda: account
    app.dependency_overrides[get_db_session] = lambda: None
    app.dependency_overrides[get_file_service] = lambda: FakeFileService()

    with TestClient(app) as client:
        response = client.get("/files?parent_id=undefined&current_page=1&page_size=20")

    assert response.status_code == 200
    assert response.json()["code"] == "success"
    assert response.json()["data"]["list"] == []
