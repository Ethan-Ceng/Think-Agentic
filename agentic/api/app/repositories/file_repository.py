#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/21 0:47
@Author  : thezehui@gmail.com
@File    : file_repository.py
"""
from datetime import datetime
from typing import Protocol, Optional

from app.core.entities.file import File


class FileRepository(Protocol):
    """文件模型数据仓库"""

    async def save(self, file: File) -> None:
        """新增或更新文件信息"""
        ...

    async def get_by_id(self, file_id: str) -> Optional[File]:
        """根据传递的文件id获取文件信息"""
        ...

    async def get_by_id_for_user(self, file_id: str, user_id: str) -> Optional[File]:
        """根据文件id和用户id获取文件信息"""
        ...

    async def list_for_user(
        self,
        user_id: str,
        *,
        parent_id: str | None,
        search_word: str = "",
        file_kind: str = "all",
        source_type: str = "all",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[File], int]:
        ...

    async def list_folders_for_user(self, user_id: str) -> list[File]:
        ...

    async def list_children(self, user_id: str, parent_id: str) -> list[File]:
        ...

    async def list_expired(self, now: datetime, limit: int = 100) -> list[File]:
        ...

    async def hard_delete(self, file_id: str) -> None:
        ...
