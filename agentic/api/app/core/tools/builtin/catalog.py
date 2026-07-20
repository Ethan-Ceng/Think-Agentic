#!/usr/bin/env python
# -*- coding: utf-8 -*-
from dataclasses import dataclass
from typing import Type

from app.core.tools.a2a import A2ATool
from app.core.tools.base import BaseTool
from app.core.tools.browser import BrowserTool
from app.core.tools.file import FileTool
from app.core.tools.message import MessageTool
from app.core.tools.search import SearchTool
from app.core.tools.shell import ShellTool


@dataclass(frozen=True)
class BuiltinToolGroup:
    name: str
    tool_cls: Type[BaseTool]
    provider_id: str
    provider_label: str
    group: str
    executor_type: str
    category: str
    description: str = ""
    requires_sandbox: bool = False
    requires_browser: bool = False
    requires_credentials: bool = False


BUILTIN_TOOL_GROUPS: tuple[BuiltinToolGroup, ...] = (
    BuiltinToolGroup(
        name="file",
        tool_cls=FileTool,
        provider_id="builtin.file",
        provider_label="文件",
        group="file",
        executor_type="builtin",
        category="文件",
        description="沙箱文件读取、写入、替换和检索工具",
        requires_sandbox=True,
    ),
    BuiltinToolGroup(
        name="shell",
        tool_cls=ShellTool,
        provider_id="builtin.shell",
        provider_label="Shell",
        group="shell",
        executor_type="builtin",
        category="Shell",
        description="沙箱命令执行、输出读取和进程控制工具",
        requires_sandbox=True,
    ),
    BuiltinToolGroup(
        name="browser",
        tool_cls=BrowserTool,
        provider_id="builtin.browser",
        provider_label="浏览器",
        group="browser",
        executor_type="builtin",
        category="浏览器",
        description="沙箱浏览器页面查看、导航、点击和控制台工具",
        requires_browser=True,
    ),
    BuiltinToolGroup(
        name="search",
        tool_cls=SearchTool,
        provider_id="builtin.search",
        provider_label="搜索",
        group="search",
        executor_type="builtin",
        category="搜索",
        description="联网搜索工具",
        requires_credentials=True,
    ),
    BuiltinToolGroup(
        name="message",
        tool_cls=MessageTool,
        provider_id="builtin.message",
        provider_label="用户消息",
        group="message",
        executor_type="builtin",
        category="用户交互",
        description="向用户发送通知或请求补充输入",
    ),
    BuiltinToolGroup(
        name="a2a",
        tool_cls=A2ATool,
        provider_id="a2a.remote",
        provider_label="A2A Agent",
        group="a2a",
        executor_type="a2a",
        category="远程 Agent",
        description="A2A 远程 Agent 卡片发现与调用工具",
        requires_credentials=True,
    ),
)


HIGH_RISK_TOOL_NAMES = {
    "shell_execute",
    "shell_write_input",
    "shell_kill_process",
    "browser_console_exec",
}

MEDIUM_RISK_TOOL_NAMES = {
    "write_file",
    "replace_in_file",
    "browser_navigate",
    "browser_restart",
    "browser_click",
    "browser_input",
    "browser_move_mouse",
    "browser_press_key",
    "browser_select_option",
    "browser_scroll_up",
    "browser_scroll_down",
    "message_ask_user",
    "call_remote_agent",
    "shell_read_output",
    "shell_wait_process",
}

BUILTIN_TOOL_LABELS = {
    "read_file": "读取文件",
    "write_file": "写入文件",
    "replace_in_file": "替换文件内容",
    "search_in_file": "搜索文件内容",
    "find_files": "查找文件",
    "shell_execute": "执行 Shell 命令",
    "shell_read_output": "读取 Shell 输出",
    "shell_wait_process": "等待 Shell 进程",
    "shell_write_input": "写入 Shell 输入",
    "shell_kill_process": "终止 Shell 进程",
    "browser_view": "查看页面",
    "browser_navigate": "导航页面",
    "browser_restart": "重启浏览器",
    "browser_click": "点击页面",
    "browser_input": "输入页面文本",
    "browser_move_mouse": "移动鼠标",
    "browser_press_key": "模拟按键",
    "browser_select_option": "选择下拉项",
    "browser_scroll_up": "向上滚动",
    "browser_scroll_down": "向下滚动",
    "browser_console_exec": "执行浏览器脚本",
    "browser_console_view": "查看浏览器控制台",
    "search_web": "搜索网页",
    "message_notify_user": "通知用户",
    "message_ask_user": "询问用户",
    "get_remote_agent_cards": "获取远程 Agent 卡片",
    "call_remote_agent": "调用远程 Agent",
}


def risk_for_builtin_function(function_name: str) -> str:
    if function_name in HIGH_RISK_TOOL_NAMES:
        return "high"
    if function_name in MEDIUM_RISK_TOOL_NAMES:
        return "medium"
    return "low"


def label_for_builtin_function(function_name: str) -> str:
    return BUILTIN_TOOL_LABELS.get(function_name, function_name)
