from __future__ import annotations

from typing import Optional, Protocol

from app.core.browser.base import Browser
from app.core.entities.tool_result import ToolResult


class BrowserRuntime(Protocol):
    async def get_browser(self) -> Browser:
        ...


class LazyBrowser:
    """Browser proxy that resolves the real browser on first async use."""

    def __init__(self, runtime: BrowserRuntime) -> None:
        self._runtime = runtime

    async def _browser(self) -> Browser:
        return await self._runtime.get_browser()

    async def view_page(self) -> ToolResult:
        return await (await self._browser()).view_page()

    async def navigate(self, url: str) -> ToolResult:
        return await (await self._browser()).navigate(url)

    async def restart(self, url: str) -> ToolResult:
        return await (await self._browser()).restart(url)

    async def click(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        return await (await self._browser()).click(
            index=index,
            coordinate_x=coordinate_x,
            coordinate_y=coordinate_y,
        )

    async def input(
        self,
        text: str,
        press_enter: bool,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        return await (await self._browser()).input(
            text=text,
            press_enter=press_enter,
            index=index,
            coordinate_x=coordinate_x,
            coordinate_y=coordinate_y,
        )

    async def move_mouse(
        self,
        coordinate_x: float,
        coordinate_y: float,
    ) -> ToolResult:
        return await (await self._browser()).move_mouse(
            coordinate_x,
            coordinate_y,
        )

    async def press_key(self, key: str) -> ToolResult:
        return await (await self._browser()).press_key(key)

    async def select_option(self, index: int, option: int) -> ToolResult:
        return await (await self._browser()).select_option(index, option)

    async def scroll_up(self, to_top: Optional[bool] = None) -> ToolResult:
        return await (await self._browser()).scroll_up(to_top)

    async def scroll_down(self, to_down: Optional[bool] = None) -> ToolResult:
        return await (await self._browser()).scroll_down(to_down)

    async def screenshot(self, full_page: Optional[bool] = None) -> bytes:
        return await (await self._browser()).screenshot(full_page)

    async def console_exec(self, javascript: str) -> ToolResult:
        return await (await self._browser()).console_exec(javascript)

    async def console_view(
        self,
        max_lines: Optional[int] = None,
    ) -> ToolResult:
        return await (await self._browser()).console_view(max_lines)
