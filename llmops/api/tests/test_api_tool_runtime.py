import httpx

from app.core.tools.api_tools.entities import ToolEntity
from app.core.tools.api_tools.providers import ApiProviderManager


def test_api_provider_manager_builds_callable_runtime_tool(monkeypatch) -> None:
    captured = {}

    def fake_request(**kwargs):
        captured.update(kwargs)
        return httpx.Response(200, text="ok", request=httpx.Request(kwargs["method"], kwargs["url"]))

    monkeypatch.setattr(httpx, "request", fake_request)
    tool = ApiProviderManager().get_tool(
        ToolEntity(
            id="provider-1",
            name="get_weather",
            url="https://example.test/weather/{city}",
            method="get",
            description="Get weather",
            headers=[{"key": "X-Test", "value": "yes"}],
            parameters=[
                {"name": "city", "in": "path", "description": "City", "required": True, "type": "str"},
                {"name": "unit", "in": "query", "description": "Unit", "required": False, "type": "str"},
            ],
        )
    )

    result = tool.invoke({"city": "Shenzhen", "unit": "c"})

    assert result == "ok"
    assert captured["url"] == "https://example.test/weather/Shenzhen"
    assert captured["params"] == {"unit": "c"}
    assert captured["headers"] == {"X-Test": "yes"}

