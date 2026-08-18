#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pytest
from pydantic import TypeAdapter, ValidationError

from app.core.entities.event import (
    Event,
    InteractionDecision,
    InteractionEvent,
    InteractionOption,
    InteractionStatus,
    InteractionType,
    MessageDeltaEvent,
    MessageEvent,
)
from app.schemas.event import (
    EventMapper,
    InteractionSSEEvent,
    MessageDeltaSSEEvent,
    MessageSSEEvent,
)


def test_interaction_event_round_trips_through_domain_union_and_sse_mapper() -> None:
    event = InteractionEvent(
        action_id="action-1",
        interaction_type=InteractionType.ASK_USER,
        status=InteractionStatus.PENDING,
        tool_call_id="call-1",
        tool_name="message",
        function_name="message_ask_user",
        function_args={"text": "选择发布环境"},
        prompt="选择发布环境",
        options=[
            InteractionOption(value="staging", label="预发布"),
            InteractionOption(value="production", label="生产"),
        ],
        allow_text=False,
    )

    restored = TypeAdapter(Event).validate_json(event.model_dump_json())
    assert isinstance(restored, InteractionEvent)
    assert restored.options[1].value == "production"

    EventMapper._cache_mapping = None
    sse = EventMapper.event_to_sse_event(restored)
    assert isinstance(sse, InteractionSSEEvent)
    assert sse.event == "interaction"
    assert sse.data.action_id == "action-1"
    assert sse.data.status == InteractionStatus.PENDING
    assert sse.data.options[0].label == "预发布"


def test_resolved_interaction_keeps_decision_and_selected_values() -> None:
    event = InteractionEvent(
        action_id="action-2",
        interaction_type=InteractionType.ASK_USER,
        status=InteractionStatus.RESOLVED,
        tool_call_id="call-2",
        tool_name="message",
        function_name="message_ask_user",
        function_args={"text": "选择范围"},
        prompt="选择范围",
        decision=InteractionDecision.ANSWER,
        answer="api, web",
        selected_values=["api", "web"],
    )

    restored = TypeAdapter(Event).validate_json(event.model_dump_json())
    assert isinstance(restored, InteractionEvent)
    assert restored.decision == InteractionDecision.ANSWER
    assert restored.selected_values == ["api", "web"]


def test_interaction_sse_redacts_sensitive_tool_arguments() -> None:
    event = InteractionEvent(
        action_id="action-sensitive",
        interaction_type=InteractionType.TOOL_APPROVAL,
        tool_call_id="call-sensitive",
        tool_name="api",
        function_name="deploy",
        function_args={
            "environment": "production",
            "headers": {"authorization": "Bearer secret"},
            "api_key": "secret-key",
        },
        prompt="Approve deploy",
        risk_level="high",
    )

    sse = EventMapper.event_to_sse_event(event)

    assert isinstance(sse, InteractionSSEEvent)
    assert sse.data.function_args["environment"] == "production"
    assert sse.data.function_args["api_key"] == "******"
    assert sse.data.function_args["headers"]["authorization"] == "******"


def test_message_delta_and_final_message_round_trip_with_stream_id() -> None:
    delta = MessageDeltaEvent(
        stream_id="stream-1",
        sequence=2,
        delta="你好",
        operation="append",
    )

    restored = TypeAdapter(Event).validate_json(delta.model_dump_json())
    assert isinstance(restored, MessageDeltaEvent)
    assert restored.role == "assistant"
    assert restored.sequence == 2

    EventMapper._cache_mapping = None
    delta_sse = EventMapper.event_to_sse_event(restored)
    assert isinstance(delta_sse, MessageDeltaSSEEvent)
    assert delta_sse.event == "message_delta"
    assert delta_sse.data.stream_id == "stream-1"
    assert delta_sse.data.delta == "你好"
    assert delta_sse.data.operation == "append"

    final = MessageEvent(message="你好", stream_id="stream-1")
    final_sse = EventMapper.event_to_sse_event(final)
    assert isinstance(final_sse, MessageSSEEvent)
    assert final_sse.data.stream_id == "stream-1"


@pytest.mark.parametrize("operation", ["unknown", "replace", "finish"])
def test_message_delta_rejects_unknown_operations(operation: str) -> None:
    with pytest.raises(ValidationError):
        MessageDeltaEvent(
            stream_id="stream-1",
            sequence=0,
            delta="text",
            operation=operation,
        )


@pytest.mark.parametrize(
    ("operation", "delta"),
    [("append", ""), ("reset", "text"), ("abort", "text")],
)
def test_message_delta_rejects_invalid_operation_payloads(
    operation: str,
    delta: str,
) -> None:
    with pytest.raises(ValidationError):
        MessageDeltaEvent(
            stream_id="stream-1",
            sequence=0,
            delta=delta,
            operation=operation,
        )
