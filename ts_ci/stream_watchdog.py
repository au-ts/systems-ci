import asyncio
import enum

from types import TracebackType
from typing import final, Optional, Type

from .backends import TeeOut

# Modified from https://github.com/python/cpython/blob/v3.14.3/Lib/asyncio/timeouts.py
# under the Zero-Clause BSD License

class _State(enum.Enum):
    CREATED = "created"
    ENTERED = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    EXITED = "finished"

@final
class StreamWatchdog:
    def __init__(self, watchdog_timeout: float, tee: TeeOut, poll_s: float = 0.5) -> None:
        self._state = _State.CREATED

        self._timeout_handler: Optional[asyncio.Handle] = None
        self._task: Optional[asyncio.Task] = None
        self._timeout = watchdog_timeout
        self._tee = tee
        self._poll_s = poll_s

    def _watchdog_kick(self) -> None:
        assert self._state is _State.ENTERED

        if self._timeout_handler is not None:
            self._timeout_handler.cancel()

        loop = asyncio.get_running_loop()
        if self._tee.last_write_age_s() >= self._timeout:
            self._timeout_handler = loop.call_soon(self._on_timeout)
        else:
            self._timeout_handler = loop.call_at(loop.time() + self._poll_s, self._watchdog_kick)

    async def __aenter__(self) -> "StreamWatchdog":
        if self._state is not _State.CREATED:
            raise RuntimeError("StreamWatchdog has already been entered")
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("StreamWatchdog should be used inside a task")
        self._state = _State.ENTERED
        self._task = task
        self._tee.touch()
        self._cancelling = self._task.cancelling()
        self._watchdog_kick()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Optional[bool]:
        assert self._state in (_State.ENTERED, _State.EXPIRING)

        if self._timeout_handler is not None:
            self._timeout_handler.cancel()
            self._timeout_handler = None

        if self._state is _State.EXPIRING:
            self._state = _State.EXPIRED

            assert self._task is not None
            if self._task.uncancel() <= self._cancelling and exc_type is not None:
                # Since there are no new cancel requests, we're
                # handling this.
                if issubclass(exc_type, asyncio.CancelledError):
                    raise TimeoutError from exc_val
                elif exc_val is not None:
                    self._insert_timeout_error(exc_val)
                    if isinstance(exc_val, ExceptionGroup):
                        for exc in exc_val.exceptions:
                            self._insert_timeout_error(exc)
        elif self._state is _State.ENTERED:
            self._state = _State.EXITED

        return None

    def _on_timeout(self) -> None:
        assert self._state is _State.ENTERED
        assert self._task is not None

        self._task.cancel()
        self._state = _State.EXPIRING
        # drop the reference early
        self._timeout_handler = None

    @staticmethod
    def _insert_timeout_error(exc_val: BaseException) -> None:
        while exc_val.__context__ is not None:
            if isinstance(exc_val.__context__, asyncio.CancelledError):
                te = TimeoutError()
                te.__context__ = te.__cause__ = exc_val.__context__
                exc_val.__context__ = te
                break
            exc_val = exc_val.__context__
