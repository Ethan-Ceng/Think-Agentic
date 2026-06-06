from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.conversation import Message
from app.services.agent_task_service import AgentTaskService
from app.services.app_service import AppService
from app.services.base_service import BaseService


@dataclass
class AnalysisService(BaseService):
    app_service: AppService = field(default_factory=AppService)
    agent_task_service: AgentTaskService = field(default_factory=AgentTaskService)

    def get_app_analysis(self, session: Session, app_id: UUID, account: Account) -> dict[str, Any]:
        app = self.app_service.get_app(session, app_id, account)
        today = datetime.now()
        today_midnight = datetime.combine(today, datetime.min.time())
        seven_days_ago = today_midnight - timedelta(days=7)
        fourteen_days_ago = today_midnight - timedelta(days=14)

        seven_days_messages = self.get_messages_by_time_range(session, app.id, seven_days_ago, today_midnight)
        fourteen_days_messages = self.get_messages_by_time_range(session, app.id, fourteen_days_ago, seven_days_ago)

        current = self.calculate_overview_indicators_by_messages(seven_days_messages)
        previous = self.calculate_overview_indicators_by_messages(fourteen_days_messages)
        pop = self.calculate_pop_by_overview_indicators(current, previous)
        trend = self.calculate_trend_by_messages(today_midnight, 7, seven_days_messages)
        fields = [
            "total_messages",
            "active_accounts",
            "avg_of_conversation_messages",
            "token_output_rate",
            "cost_consumption",
        ]
        return {**trend, **{field: {"data": current[field], "pop": pop[field]} for field in fields}}

    def get_app_agent_runtime_analysis(
        self,
        session: Session,
        app_id: UUID,
        account: Account,
        *,
        from_ts: int | None = None,
        to_ts: int | None = None,
        status: str = "all",
        user_id: str = "all",
        router_agent_id: str = "all",
        worker_agent_id: str = "all",
        group_by: str = "day",
    ) -> dict[str, Any]:
        return self.agent_task_service.get_app_task_runtime_metrics(
            session,
            app_id=app_id,
            account=account,
            from_ts=from_ts,
            to_ts=to_ts,
            status=status,
            user_id=user_id,
            router_agent_id=router_agent_id,
            worker_agent_id=worker_agent_id,
            group_by=group_by,
        )

    @staticmethod
    def get_messages_by_time_range(
        session: Session,
        app_id: UUID,
        start_at: datetime,
        end_at: datetime,
    ) -> list[Message]:
        return list(
            session.query(Message)
            .filter(
                Message.app_id == app_id,
                Message.created_at >= start_at,
                Message.created_at < end_at,
                Message.answer != "",
            )
            .all()
        )

    @classmethod
    def calculate_overview_indicators_by_messages(cls, messages: list[Message]) -> dict[str, Any]:
        total_messages = len(messages)
        active_accounts = len({message.created_by for message in messages})
        conversation_count = len({message.conversation_id for message in messages})
        avg_of_conversation_messages = total_messages / conversation_count if conversation_count else 0
        latency_sum = sum(float(message.latency or 0) for message in messages)
        token_output_rate = (
            sum(int(message.total_token_count or 0) for message in messages) / latency_sum if latency_sum else 0
        )
        cost_consumption = sum(float(message.total_price or 0) for message in messages)
        return {
            "total_messages": total_messages,
            "active_accounts": active_accounts,
            "avg_of_conversation_messages": float(avg_of_conversation_messages),
            "token_output_rate": float(token_output_rate),
            "cost_consumption": float(cost_consumption),
        }

    @classmethod
    def calculate_pop_by_overview_indicators(
        cls,
        current_data: dict[str, Any],
        previous_data: dict[str, Any],
    ) -> dict[str, Any]:
        fields = [
            "total_messages",
            "active_accounts",
            "avg_of_conversation_messages",
            "token_output_rate",
            "cost_consumption",
        ]
        pop = {}
        for metric in fields:
            previous_value = previous_data.get(metric) or 0
            current_value = current_data.get(metric) or 0
            pop[metric] = float((current_value - previous_value) / previous_value) if previous_value else 0
        return pop

    @classmethod
    def calculate_trend_by_messages(cls, end_at: datetime, days_ago: int, messages: list[Message]) -> dict[str, Any]:
        end_at = datetime.combine(end_at, datetime.min.time())
        trend = {
            "total_messages_trend": {"x_axis": [], "y_axis": []},
            "active_accounts_trend": {"x_axis": [], "y_axis": []},
            "avg_of_conversation_messages_trend": {"x_axis": [], "y_axis": []},
            "cost_consumption_trend": {"x_axis": [], "y_axis": []},
        }
        for day in range(days_ago):
            start = end_at - timedelta(days_ago - day)
            end = end_at - timedelta(days_ago - day - 1)
            bucket = [message for message in messages if start <= message.created_at < end]
            conversation_count = len({message.conversation_id for message in bucket})
            total_messages = len(bucket)
            timestamp = int(start.timestamp())
            trend["total_messages_trend"]["x_axis"].append(timestamp)
            trend["total_messages_trend"]["y_axis"].append(total_messages)
            trend["active_accounts_trend"]["x_axis"].append(timestamp)
            trend["active_accounts_trend"]["y_axis"].append(len({message.created_by for message in bucket}))
            trend["avg_of_conversation_messages_trend"]["x_axis"].append(timestamp)
            trend["avg_of_conversation_messages_trend"]["y_axis"].append(
                float(total_messages / conversation_count if conversation_count else 0)
            )
            trend["cost_consumption_trend"]["x_axis"].append(timestamp)
            trend["cost_consumption_trend"]["y_axis"].append(
                float(sum(float(message.total_price or 0) for message in bucket))
            )
        return trend
