from runa.core import Event, EventType


def test_event_has_unique_id_and_timestamp():
    a = Event(type=EventType.RUN_STARTED)
    b = Event(type=EventType.RUN_STARTED)
    assert a.id != b.id
    assert a.timestamp is not None
