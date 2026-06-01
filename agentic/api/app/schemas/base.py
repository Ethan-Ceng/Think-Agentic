#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一响应结构
"""
from typing import TypeVar, Generic, Optional

from pydantic import BaseModel, Field

T = TypeVar("T")


class Response(BaseModel, Generic[T]):
    """基础API响应结构"""
    code: int = 200
    msg: str = "success"
    data: Optional[T] = Field(default_factory=dict)

    @staticmethod
    def success(data: Optional[T] = None, msg: str = "success") -> "Response[T]":
        return Response(code=200, msg=msg, data=data if data is not None else {})

    @staticmethod
    def fail(code: int, msg: str, data: Optional[T] = None) -> "Response[T]":
        return Response(code=code, msg=msg, data=data if data is not None else {})
