import asyncio

from shared.python.lab_core.contracts import CorrelationContext
from services.gateway.app.faults import FaultProfile


def collect(profile: FaultProfile, operation: str):
    ctx = CorrelationContext(run_id="00000000-0000-0000-0000-000000000001", request_id="req-1")

    async def source():
        yield b"first"
        yield b"second"

    async def run():
        return [chunk async for chunk in profile.apply(ctx, operation, source())]

    return asyncio.run(run())


def test_duplicate_fault_replays_each_stream_chunk():
    assert collect(FaultProfile({"message/stream": {"type": "duplicate"}}), "message/stream") == [
        b"first",
        b"first",
        b"second",
        b"second",
    ]


def test_drop_stream_fault_emits_no_chunks():
    assert collect(FaultProfile({"message/stream": {"type": "drop_stream"}}), "message/stream") == []


def test_malformed_fault_replaces_the_response():
    assert collect(FaultProfile({"message/send": {"type": "malformed"}}), "message/send") == [b"{"]
