#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/24 14:55
@Author  : thezehui@gmail.com
@File    : search.py
"""
from typing import Protocol, Optional

from app.core.entities.search import SearchResults
from app.core.entities.tool_result import ToolResult


class SearchEngine(Protocol):
    """搜索引擎API接口协议"""

    async def invoke(self, query: str, date_range: Optional[str] = None) -> ToolResult[SearchResults]:
        """调用搜索引擎并传递query+date_range(日期检索范围)调用搜索引擎获取数据"""
        ...
