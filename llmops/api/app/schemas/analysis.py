from pydantic import BaseModel, Field


class TrendData(BaseModel):
    x_axis: list[int]
    y_axis: list[float]


class IndicatorData(BaseModel):
    data: float
    pop: float


class AppAnalysisResponse(BaseModel):
    total_messages_trend: TrendData
    active_accounts_trend: TrendData
    avg_of_conversation_messages_trend: TrendData
    cost_consumption_trend: TrendData
    total_messages: IndicatorData
    active_accounts: IndicatorData
    avg_of_conversation_messages: IndicatorData
    token_output_rate: IndicatorData
    cost_consumption: IndicatorData


class GetAppAgentRuntimeAnalysisRequest(BaseModel):
    from_ts: int | None = Field(None, ge=0)
    to_ts: int | None = Field(None, ge=0)
    status: str = "all"
    user_id: str = "all"
    router_agent_id: str = "all"
    worker_agent_id: str = "all"
    group_by: str = "day"
