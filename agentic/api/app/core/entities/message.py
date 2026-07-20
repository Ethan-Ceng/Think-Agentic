#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/20 9:58
@Author  : thezehui@gmail.com
@File    : message.py
"""
from typing import List, Optional

from pydantic import BaseModel, Field

from .event import InteractionResolution


class Message(BaseModel):
    """用户传递的消息"""
    message: str = ""  # 用户发送的消息
    attachments: List[str] = Field(default_factory=list)  # 用户发送的附件
    interaction_response: Optional[InteractionResolution] = None
