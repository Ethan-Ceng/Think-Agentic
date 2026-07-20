#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/21 10:26
@Author  : thezehui@gmail.com
@File    : react.py
"""
import logging
from typing import AsyncGenerator

from app.core.entities.event import (
    InteractionEvent,
    InteractionResolution,
    StepEventStatus,
    StepEvent,
    ToolEvent,
    MessageEvent,
    ErrorEvent,
    WaitEvent,
    BaseEvent
)
from app.core.entities.file import File
from app.core.entities.message import Message
from app.core.entities.plan import Plan, Step, ExecutionStatus
from app.core.prompts.react import REACT_SYSTEM_PROMPT, EXECUTION_PROMPT, SUMMARIZE_PROMPT
from app.core.prompts.system import SYSTEM_PROMPT
from .base import BaseAgent

logger = logging.getLogger(__name__)


class ReActAgent(BaseAgent):
    """基于ReAct架构的执行Agent"""
    name: str = "react"
    _system_prompt: str = SYSTEM_PROMPT + REACT_SYSTEM_PROMPT
    _format: str = "json_object"  # format控制的是content、工具调用控制的是tool_calls两者不冲突

    async def execute_step(self, plan: Plan, step: Step, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """根据传递的消息+规划+子步骤，执行相应的子步骤"""
        # 1.根据传递的内容生成执行消息
        query = EXECUTION_PROMPT.format(
            message=message.message,
            attachments="\n".join(message.attachments),
            language=plan.language,
            step=step.description,
        )

        # 2.更新步骤的执行状态为运行中并返回Step事件
        step.status = ExecutionStatus.RUNNING
        yield StepEvent(step=step, status=StepEventStatus.STARTED)

        # 3.调用invoke获取agent返回的事件内容
        async for event in self.invoke(query):
            # 4.判断事件类型执行不同操作
            if isinstance(event, InteractionEvent):
                yield event
                yield WaitEvent()
                return
            if isinstance(event, ToolEvent):
                pass
            elif isinstance(event, MessageEvent):
                # 8.返回消息事件，意味着content有内容，content有内容则代表执行Agent已运行完毕
                step.status = ExecutionStatus.COMPLETED

                # 9.message中输出的数据结构为json，需要提取并解析
                parsed_obj = await self._json_parser.invoke(event.message)
                new_step = Step.model_validate(parsed_obj)

                # 10.更新子步骤的数据
                step.success = new_step.success
                step.result = new_step.result
                step.attachments = new_step.attachments

                # 11.返回步骤完成事件
                yield StepEvent(step=step, status=StepEventStatus.COMPLETED)

                # 12.如果子步骤拿到了结果，还需要返回一段消息给用户(将结果返回给用户)
                if step.result:
                    yield MessageEvent(role="assistant", message=step.result)
                continue
            elif isinstance(event, ErrorEvent):
                # 13.错误事件更新步骤的状态
                step.status = ExecutionStatus.FAILED
                step.error = event.error

                # 14.返回子步骤对应事件
                yield StepEvent(step=step, status=StepEventStatus.FAILED)

            # 15.其他场景将事件直接返回
            yield event

        # 16.循环迭代完成后代表子步骤已实现，需要更新状态
        step.status = ExecutionStatus.COMPLETED

    async def resume_step(
            self,
            plan: Plan,
            step: Step,
            resolution: InteractionResolution,
    ) -> AsyncGenerator[BaseEvent, None]:
        """恢复被结构化询问或工具审批暂停的当前步骤。"""
        step.status = ExecutionStatus.RUNNING
        async for event in self.resume_interaction(resolution):
            if isinstance(event, InteractionEvent):
                yield event
                yield WaitEvent()
                return
            if isinstance(event, MessageEvent):
                parsed_obj = await self._json_parser.invoke(event.message)
                new_step = Step.model_validate(parsed_obj)
                step.status = ExecutionStatus.COMPLETED
                step.success = new_step.success
                step.result = new_step.result
                step.attachments = new_step.attachments
                yield StepEvent(step=step, status=StepEventStatus.COMPLETED)
                if step.result:
                    yield MessageEvent(role="assistant", message=step.result)
                continue
            if isinstance(event, ErrorEvent):
                step.status = ExecutionStatus.FAILED
                step.error = event.error
                yield StepEvent(step=step, status=StepEventStatus.FAILED)
            yield event

    async def summarize(self) -> AsyncGenerator[BaseEvent, None]:
        """调用Agent汇总历史的消息并生成最终回复+附件"""
        # 1.构建请求query
        query = SUMMARIZE_PROMPT

        # 2.调用invoke方法获取Agent生成的事件
        async for event in self.invoke(query):
            # 3.判断事件类型是否为消息事件，如果是则表示Agent结构化生成汇总内容
            if isinstance(event, MessageEvent):
                # 4.记录日志并解析输出内容
                logger.info(f"执行Agent生成汇总内容: {event.message}")
                parsed_obj = await self._json_parser.invoke(event.message)

                # 5.将解析数据转换为Message对象
                message = Message.model_validate(parsed_obj)

                # 6.提取消息中的附件信息
                attachments = [File(filepath=filepath) for filepath in message.attachments]

                # 7.返回消息事件并将消息+附件进行相应
                yield MessageEvent(
                    role="assistant",
                    message=message.message,
                    attachments=attachments,
                )
            else:
                # 8.其他事件则直接返回
                yield event
