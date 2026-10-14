"""FIX14 test-only child bootstrap and child-side test coroutines.

Imported first inside the runner's child: allows loopback sockets only (attempts are logged to
FIX14_TEST_BLOCKED_LOG), optionally shortens the readers' request deadline, ignores SIGTERM or stalls
before reading the CALL frame. Never imported by production code.
"""

import asyncio
import os
import signal
import socket
import sys
import time

_LOCAL = {"127.0.0.1", "::1", "localhost"}
_connect, _connect_ex, _getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo


def _guard(address):
    if isinstance(address, tuple) and str(address[0]) not in _LOCAL:
        if os.environ.get("FIX14_TEST_BLOCKED_LOG"):
            with open(os.environ["FIX14_TEST_BLOCKED_LOG"], "a") as log:
                log.write(f"{address[0]}\n")
        raise OSError("FIX14 offline test: external network blocked")


def _guarded_connect(self, address):
    _guard(address)
    return _connect(self, address)


def _guarded_connect_ex(self, address):
    _guard(address)
    return _connect_ex(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if host is not None:
        _guard((host.decode() if isinstance(host, bytes) else host, 0))
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
socket.getaddrinfo = _guarded_getaddrinfo

if os.environ.get("FIX14_TEST_REQUEST_TIMEOUT_S"):
    import fix10a_goal_direction
    import fix10a_vision_providers
    import identity_verify

    for _module in (fix10a_goal_direction, fix10a_vision_providers, identity_verify):
        _module.VERIFY_REQUEST_TIMEOUT_S = float(os.environ["FIX14_TEST_REQUEST_TIMEOUT_S"])

if os.environ.get("FIX14_TEST_IGNORE_SIGTERM"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if os.environ.get("FIX14_TEST_STALL_BEFORE_CALL_S"):
    time.sleep(float(os.environ["FIX14_TEST_STALL_BEFORE_CALL_S"]))

_KEEP = []


async def echo(value):
    await asyncio.sleep(0)
    return value


async def _absorb_cancellations(times):
    loop = asyncio.get_running_loop()
    for _ in range(times):
        try:
            await loop.create_future()
        except asyncio.CancelledError:
            pass
    await loop.create_future()


async def resistant_task_then(value):
    _KEEP.append(asyncio.get_running_loop().create_task(_absorb_cancellations(1), name="fix14-resistant"))
    await asyncio.sleep(0)
    return value


async def uncancellable_task_then(value):
    _KEEP.append(asyncio.get_running_loop().create_task(_absorb_cancellations(10**9), name="fix14-uncancellable"))
    await asyncio.sleep(0)
    return value


async def ignore_cancel_forever():
    await _absorb_cancellations(10**9)


async def ignore_sigterm_and_block():
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(600)


async def hard_exit():
    os._exit(7)


async def external_connect():
    try:
        socket.create_connection(("203.0.113.10", 80), timeout=2).close()
    except OSError as exc:
        return f"blocked:{exc}"
    return "connected"


async def partial_reply_then_stall():
    header = sys.modules["__main__"]._HEADER
    os.write(int(sys.argv[3]), header.pack(1 << 20) + b"partial")
    time.sleep(600)


async def print_then(value):
    print("FIX14-CHILD-OUTPUT stdout")
    sys.stderr.write("FIX14-CHILD-OUTPUT stderr\n")
    return value


ADVISORY = (
    "Sending a large body directly with raw bytes might lock the event loop. "
    "You should probably pass an io.BytesIO object instead"
)


def _advisory_line_number():
    import inspect

    import aiohttp.payload

    lines, start = inspect.getsourcelines(aiohttp.payload.BytesPayload.__init__)
    return next(start + i for i, text in enumerate(lines) if "warnings.warn(" in text)


async def genuine_large_body_advisory_then(value, extra_output=None):
    import aiohttp.payload

    aiohttp.payload.BytesPayload(b"\0" * (aiohttp.payload.TOO_LARGE_BYTES_BODY + 1))
    if extra_output == "copy":
        print(f"{aiohttp.payload.__file__}:{_advisory_line_number()}: ResourceWarning: {ADVISORY}", flush=True)
    elif extra_output == "other":
        print("ResourceWarning: fix14 unaccounted resource", flush=True)
    return value


async def advisory_text_from_unrelated_source_then(value, where):
    import warnings

    import aiohttp.payload

    filename, lineno = {
        "other_file": ("/tmp/fix14_unrelated/payload.py", _advisory_line_number()),
        "other_line": (aiohttp.payload.__file__, 1),
    }[where]
    warnings.warn_explicit(ADVISORY, ResourceWarning, filename, lineno)
    return value


async def unknown_resource_warning_then(value):
    import warnings

    warnings.warn("fix14 unknown resource", ResourceWarning)
    return value


async def leaked_client_session_then(value):
    import aiohttp

    aiohttp.ClientSession()  # never closed: a real leak
    await asyncio.sleep(0)
    return value


async def output_around_genuine_advisory_then(value, leading=b"", filler_lines=0, pad_to=None):
    """Raw fd writes keep the child's combined output size exact; leading text is output, not a warning."""
    import os

    import aiohttp.payload

    os.write(1, leading + b"x\n" * filler_lines)
    aiohttp.payload.BytesPayload(b"\0" * (aiohttp.payload.TOO_LARGE_BYTES_BODY + 1))
    sys.stderr.flush()
    sys.stdout.flush()
    if pad_to is not None:
        os.write(1, b"x" * (pad_to - os.fstat(1).st_size - 1) + b"\n")
    return value
