#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2025/05/20 15:27
@Author  : thezehui@gmail.com
@File    : planner.py
"""
import logging
import json
from typing import Optional, AsyncGenerator

from app.core.entities.event import BaseEvent, MessageEvent, PlanEvent, PlanEventStatus
from app.core.entities.message import Message
from app.core.entities.plan import Plan, Step
from app.core.prompts.catalog import (
    PromptLocale,
    get_planner_prompts,
    infer_prompt_locale,
)
from .base import BaseAgent

"""
多Agent系统/flow=PlannerAgent+ReActAgent

顺序:
1. PlannerAgent生成规划;
2. 循环取出规划中的子步骤，让ReActAgent执行，依次迭代;
3. ReActAgent执行完每一个子步骤之后，需要将子步骤结果+Plan传递给PlannerAgent让其更新计划/Plan；
4. 循环取出规划中的子步骤，让ReActAgent执行，依次迭代;
5. ...
6. 直到所有子任务/步骤都完成，这时候将子步骤的所有结果汇总进行总结(ReActAgent);

PlannerAgent:
- 功能: 将用户的需求拆解成多个子任务+根据已完成的子任务更新规划
- 提示词: 创建规划的prompt、更新规划的prompt

ReActAgent:
- 功能: 迭代执行完每一个子任务、汇总所有的子任务进行总结
- 提示词: 执行任务的prompt、汇总总结prompt
"""

logger = logging.getLogger(__name__)
_DEFAULT_PROMPTS = get_planner_prompts(PromptLocale.ZH)


class PlannerAgent(BaseAgent):
    """规划Agent，用于将用户的任务/需求拆解成多个子步骤"""
    name: str = "planner"
    _system_prompt: str = _DEFAULT_PROMPTS.system
    _format: Optional[str] = "json_object"
    _tool_choice: Optional[str] = "none"

    def _get_available_tools(self) -> list[dict]:
        """Planner selects capability groups and never receives full Tool schemas."""
        return []

    def _capability_catalog(self) -> str:
        catalog = (
            self._tool_registry.list_capability_catalog()
            if self._tool_registry
            else []
        )
        return json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))

    def _validate_plan_capabilities(self, plan: Plan) -> None:
        if self._tool_registry is None:
            return
        known = self._tool_registry.capability_groups()
        for step in plan.steps:
            step.capabilities = [
                capability
                for capability in step.capabilities
                if capability in known
            ]

    async def create_plan(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """根据用户传递的消息创建计划/规划，迭代返回对应的事件"""
        self.set_runtime_tool_scope([])
        prompts = get_planner_prompts(infer_prompt_locale(message.message))
        self.set_runtime_system_prompt(prompts.system)
        # 1.根据用户传递的消息生成创建plan的提示词
        query = prompts.create.format(
            message=message.message,
            attachments="\n".join(message.attachments),
            capability_catalog=self._capability_catalog(),
        )

        # 2.调用invoke函数返回迭代事件
        async for event in self.invoke(query):
            # 3.规划智能体因为使用json_object，正常情况下会返回MessageEvent
            if isinstance(event, MessageEvent):
                # 4.记录日志并使用json解析器解析得到对应的数据
                logger.info(f"PlannerAgent生成消息: {event.message}")
                parsed_obj = await self._json_parser.invoke(event.message)

                # 5.将解析对象转换成Plan计划
                plan = Plan.model_validate(parsed_obj)
                self._validate_plan_capabilities(plan)

                # 6.返回PlanEvent表示规划创建成功
                yield PlanEvent(plan=plan, status=PlanEventStatus.CREATED)
            else:
                # 返回不是消息事件的事件
                yield event

    async def update_plan(self, plan: Plan, step: Step) -> AsyncGenerator[BaseEvent, None]:
        """根据传递的原始规划+子步骤更新事件"""
        self.set_runtime_tool_scope([])
        prompts = get_planner_prompts(plan.language)
        self.set_runtime_system_prompt(prompts.system)
        # 1.使用plan+step创建更新Plan提示词
        query = prompts.update.format(
            plan=plan.model_dump_json(),
            step=step.model_dump_json(),
            capability_catalog=self._capability_catalog(),
        )

        # 2.调用invoke获取对应的事件
        async for event in self.invoke(query):
            # 3.判断规划Agent生成的事件是不是消息事件
            if isinstance(event, MessageEvent):
                # 4.记录日志并解析json
                logger.info(f"PlannerAgent生成消息: {event.message}")
                parsed_obj = await self._json_parser.invoke(event.message)

                # 5.将解析对象转换成Plan
                updated_plan = Plan.model_validate(parsed_obj)
                self._validate_plan_capabilities(updated_plan)

                # 6.拷贝更新计划中的steps，避免造成数据污染
                new_steps = [Step.model_validate(step) for step in updated_plan.steps]

                # 7.查询旧计划中第一个未完成的计划
                first_pending_index = None
                for idx, candidate in enumerate(plan.steps):
                    if not candidate.done:
                        first_pending_index = idx
                        break

                # 失败发生在最后一步时，仍允许把修复步骤追加到失败历史之后。
                if first_pending_index is None and (
                    not step.success or step.needs_replan
                ):
                    current_index = next(
                        (
                            idx
                            for idx, current in enumerate(plan.steps)
                            if current.id == step.id
                        ),
                        len(plan.steps) - 1,
                    )
                    first_pending_index = current_index + 1

                # 8.判断是否有未完成的步骤，如果有则执行更新
                if first_pending_index is not None:
                    # 9.获取历史已完成的子步骤并更新
                    updated_steps = plan.steps[:first_pending_index]
                    updated_steps.extend(new_steps)

                    # 10.更新plan规划
                    plan.steps = updated_steps

                # 11.返回规划更新事件
                yield PlanEvent(plan=plan, status=PlanEventStatus.UPDATED)
            else:
                # 其他事件则直接返回
                yield event
