from app.core.entities.memory import Memory


def tool_message(call_id: str, content: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "function_name": "search_web",
        "content": content,
    }


def test_compact_consumed_tool_results_preserves_recent_protocol_messages() -> None:
    memory = Memory(
        messages=[
            {"role": "system", "content": "system"},
            tool_message("old-1", "a" * 5000),
            tool_message("old-2", "b" * 5000),
            tool_message("recent", "c" * 5000),
        ]
    )

    compacted = memory.compact_consumed_tool_results(
        preserve_recent=1,
        min_content_chars=1000,
    )

    assert compacted == 2
    assert memory.messages[1]["content"].startswith("(compacted")
    assert memory.messages[2]["content"].startswith("(compacted")
    assert memory.messages[3]["content"] == "c" * 5000
    assert [message.get("tool_call_id") for message in memory.messages[1:]] == [
        "old-1",
        "old-2",
        "recent",
    ]
