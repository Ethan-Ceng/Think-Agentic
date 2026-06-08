#!/usr/bin/env python
# -*- coding: utf-8 -*-
from typing import List

from app.core.browser.base import Browser
from app.core.sandbox.base import Sandbox
from app.core.search.base import SearchEngine
from app.core.tools.a2a import A2ATool
from app.core.tools.base import BaseTool
from app.core.tools.browser import BrowserTool
from app.core.tools.file import FileTool
from app.core.tools.mcp import MCPTool
from app.core.tools.message import MessageTool
from app.core.tools.search import SearchTool
from app.core.tools.shell import ShellTool


def build_builtin_runtime_tools(
    sandbox: Sandbox,
    browser: Browser,
    search_engine: SearchEngine,
    mcp_tool: MCPTool,
    a2a_tool: A2ATool,
) -> List[BaseTool]:
    return [
        FileTool(sandbox=sandbox),
        ShellTool(sandbox=sandbox),
        BrowserTool(browser=browser),
        SearchTool(search_engine=search_engine),
        MessageTool(),
        mcp_tool,
        a2a_tool,
    ]
