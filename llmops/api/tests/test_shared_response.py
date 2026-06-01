import json

from starlette.responses import StreamingResponse

from app.shared.response import HttpCode, compact_generate_response, success_json
from app.shared.response.response import Response


def test_success_json_uses_legacy_payload_shape() -> None:
    response = success_json({"id": "app-1"})

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "code": HttpCode.SUCCESS,
        "message": "",
        "data": {"id": "app-1"},
    }


def test_compact_generate_response_supports_streaming() -> None:
    response = compact_generate_response(item for item in ["event: ping\n\n"])

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


def test_compact_generate_response_supports_block_response() -> None:
    response = compact_generate_response(Response(data={"ok": True}))

    assert response.status_code == 200
    assert json.loads(response.body)["data"] == {"ok": True}
