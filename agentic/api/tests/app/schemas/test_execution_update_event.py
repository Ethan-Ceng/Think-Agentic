from app.core.entities.event import ExecutionUpdateEvent
from app.schemas.event import EventMapper


def test_execution_update_maps_to_dedicated_sse_contract() -> None:
    event = ExecutionUpdateEvent(
        run_id="run-1",
        input_event_id="input-1",
        nodes=[
            {
                "node_id": "run:run-1",
                "kind": "run",
                "cursor": 1,
            }
        ],
        next_cursor=1,
    )

    mapped = EventMapper.event_to_sse_event(event)

    assert mapped.event == "execution_update"
    assert mapped.data.run_id == "run-1"
    assert mapped.data.input_event_id == "input-1"
    assert mapped.data.next_cursor == 1
