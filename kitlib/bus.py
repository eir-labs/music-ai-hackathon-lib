"""The shared bus: one OSC endpoint, sending and listening.

    from kitlib import Bus

    bus = Bus()                                  # send to 127.0.0.1:9000
    bus.send("/sensor/radar", 12.3, 0.8)

    sink = Bus()                                 # listen on 0.0.0.0:9000
    @sink.on("/sensor/*")
    def show(address, *args):
        print(address, args)
    sink.serve_forever()

A Bus binds the listening socket lazily, on the first ``serve_forever`` or
``start``. That matters at this event: a radar source and a Wwise sink running
on one laptop both construct a Bus, and only the sink should hold port 9000.

Addresses passed to ``on`` may be glob patterns, so ``/sensor/*`` catches every
sensor and ``/wwise/*`` every Wwise verb.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional, Tuple

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from .contract import HOST, PORT

Handler = Callable[..., None]

#: How often a serving socket checks whether it has been asked to stop. Keeps
#: Ctrl-C snappy at the cost of twenty idle wakeups a second.
POLL_INTERVAL = 0.05


class Bus:
    """Send to ``host:port``, listen on ``bind:listen_port``.

    ``listen_port`` defaults to ``port``, which is what a source or a sink
    wants. Set them apart to forward: ``Bus(port=9001, listen_port=9000)``
    listens on the shared bus and re-sends somewhere else.
    """

    def __init__(self, host: str = HOST, port: int = PORT,
                 bind: str = "0.0.0.0", listen_port: Optional[int] = None):
        self.host = host
        self.port = int(port)
        self.bind = bind
        self.listen_port = self.port if listen_port is None else int(listen_port)
        self._client = SimpleUDPClient(self.host, self.port)
        self._dispatcher = Dispatcher()
        self._server: Optional[ThreadingOSCUDPServer] = None
        self._thread: Optional[threading.Thread] = None

    # -- sending ---------------------------------------------------------

    def send(self, address: str, *args) -> None:
        """Send one message. No args is legal; Wwise's stop verb uses that."""
        self._client.send_message(address, list(args))

    # -- listening -------------------------------------------------------

    def on(self, address: str, handler: Optional[Handler] = None):
        """Register a handler for an address or glob. Usable as a decorator.

        The handler is called as ``handler(address, *args)``.
        """
        if handler is None:
            def decorate(fn: Handler) -> Handler:
                self._dispatcher.map(address, fn)
                return fn
            return decorate
        self._dispatcher.map(address, handler)
        return handler

    def on_default(self, handler: Optional[Handler] = None):
        """Handle everything that no other handler claimed. What monitor uses."""
        if handler is None:
            def decorate(fn: Handler) -> Handler:
                self._dispatcher.set_default_handler(fn)
                return fn
            return decorate
        self._dispatcher.set_default_handler(handler)
        return handler

    # -- running ---------------------------------------------------------

    def _server_or_bind(self) -> ThreadingOSCUDPServer:
        if self._server is None:
            self._server = ThreadingOSCUDPServer((self.bind, self.listen_port),
                                                 self._dispatcher)
        return self._server

    @property
    def bound(self) -> Optional[Tuple[str, int]]:
        """Where we are actually listening, once bound. ``None`` before that.

        Pass ``listen_port=0`` to let the OS choose one and read it back here.
        """
        return None if self._server is None else self._server.server_address

    def serve_forever(self) -> None:
        """Listen on this thread until ``stop`` or Ctrl-C."""
        self._server_or_bind().serve_forever(poll_interval=POLL_INTERVAL)

    def start(self) -> threading.Thread:
        """Listen on a background thread. Returns it, already started."""
        server = self._server_or_bind()
        self._thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": POLL_INTERVAL},
            daemon=True, name=f"kitlib-bus-{self.listen_port}")
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        """Stop serving. The socket stays bound; ``close`` releases it."""
        if self._server is not None:
            self._server.shutdown()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def close(self) -> None:
        self.stop()
        if self._server is not None:
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "Bus":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        return (f"Bus(send={self.host}:{self.port}, "
                f"listen={self.bind}:{self.listen_port})")
