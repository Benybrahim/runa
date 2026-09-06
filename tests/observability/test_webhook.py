import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from runa.agent import Agent
from runa.background import ThreadQueue
from runa.core import EventType, Message, Role, Run
from runa.observability import instrument, webhook
from runa.runtime import Executor
from tests.fakes import FakeAsyncProvider


class GreeterAgent(Agent):
    instructions = "Say hello."


class _RecordingServer:
    """A real local HTTP server that records each POST body it receives."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        lock = threading.Lock()
        received = self.received

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                with lock:
                    received.append(body)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args: object) -> None:
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/"

    def close(self) -> None:
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()


def test_webhook_posts_each_event_as_json():
    server = _RecordingServer()
    try:
        provider = FakeAsyncProvider(
            responses=[Message(role=Role.ASSISTANT, content="hi")]
        )
        run = Run(input="hello")

        instrument(run, webhook(server.url, run_id=run.id))
        asyncio.run(Executor(provider).run(GreeterAgent(), run))

        assert [body["type"] for body in server.received] == [
            EventType.RUN_STARTED.value,
            EventType.MODEL_CALLED.value,
            EventType.MODEL_RESPONDED.value,
            EventType.RUN_COMPLETED.value,
        ]
        assert all(body["run_id"] == run.id for body in server.received)
        assert all("timestamp" in body and "id" in body for body in server.received)
    finally:
        server.close()


def test_webhook_with_a_queue_does_not_block_the_run():
    server = _RecordingServer()
    queue = ThreadQueue(max_workers=2)
    try:
        provider = FakeAsyncProvider(
            responses=[Message(role=Role.ASSISTANT, content="hi")]
        )
        run = Run(input="hello")

        instrument(run, webhook(server.url, run_id=run.id, queue=queue))
        asyncio.run(Executor(provider).run(GreeterAgent(), run))
        queue.close(wait=True)

        assert len(server.received) == len(run.events)
    finally:
        server.close()
