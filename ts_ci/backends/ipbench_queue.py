#!/usr/bin/env python3
# Copyright 2026, UNSW
# SPDX-License-Identifier: BSD-2-Clause

import os
from signal import SIGHUP
import asyncio
from asyncio.subprocess import PIPE, STDOUT, Process
from pathlib import Path
import sys
from typing import Optional

from .. import log
from .base import HardwareBackend
from .common import LockedBoardException, TestRetryException
from .streams import wait_for_output
from .machine_queue import MachineQueueBackend

BOOT_TIMEOUT = 2 * 60  # 2 minutes
# In case we somehow break and don't release the lock automatically.
# TODO: inherit from somewhere else
LOCK_TIMEOUT = 60 * 60  # 60 minutes
# For Github Actions etc.
IS_CI = bool(os.environ.get("CI"))


def flatten(xss):
    return [x for xs in xss for x in xs]


class IpBenchQueueBackend(HardwareBackend):
    def __init__(
        self,
        lock_group: str,
        mq_backend: MachineQueueBackend,
        benchmark_script: Path,
    ):
        self.lock_group = lock_group
        self.benchmark_script = benchmark_script
        self.mq_backend = mq_backend
        self.process: Optional[Process] = None

        if IS_CI:
            self.job_key = "-".join(
                [
                    "au_ts_ci",
                    os.environ.get("GITHUB_REPOSITORY", "??"),
                    os.environ.get("GITHUB_WORKFLOW", "??"),
                    os.environ.get("GITHUB_RUN_ID", "??"),
                    os.environ.get("GITHUB_JOB", "??"),
                    os.environ.get("INPUT_INDEX", "$0")[1:],
                ]
            )
        else:
            self.job_key = "au_ts_ci (running locally)"

    async def _acquire_lock(self):
        get_lock = await asyncio.create_subprocess_exec(
            # fmt: off
            "iq.sh", "sem",
            "-wait", self.lock_group,
            "-k", self.job_key,
            "-T", str(LOCK_TIMEOUT),
            # only try to acquire once.
            "-t", "0",
            # fmt: on
            stdout=None,  # inherit -> print
            stderr=None,  # inherit -> print
        )

        return_code = await get_lock.wait()
        if return_code != 0:
            raise LockedBoardException([self.lock_group])

        log.info(f"Acquired lock for {self.lock_group}")

    async def _release_lock(self):
        release_lock = await asyncio.create_subprocess_exec(
            # fmt: off
            "iq.sh", "sem",
            "-signal", self.lock_group,
            "-k", self.job_key,
            # fmt: on
            stdout=None,  # inherit -> print
            stderr=None,  # inherit -> print
        )

        return_code = await release_lock.wait()
        assert return_code == 0, "couldn't unlock group for unknown reason"

        log.info(f"Released locks for {self.lock_group}")

    async def start(self):
        assert self.process is None, "start() should only be called once"

        await self._acquire_lock()

        await self.mq_backend.start()

        # For IpBench, we don't start until we are called to start the benchmark

    async def begin_benchmark(self, *bench_script_args: str):
        assert self.process is None, "begin_benchmark() should only be called once"

        self.process = await asyncio.create_subprocess_exec(
            # fmt: off
            "iq.sh", "run",
            "-c", self.lock_group,
            "-f", self.benchmark_script.resolve(),
            "-k", self.job_key,
            "-n",  # don't touch the lock, we already have it.
            "--",
            *bench_script_args,
            # fmt: on
            stdin=PIPE,
            stdout=PIPE,
            stderr=STDOUT,
        )

    async def stop(self):
        # Try to stop our child
        await self.mq_backend.stop()

        if self.process is None:
            return

        await self._release_lock()

        try:
            # Use SIGHUP to close the console
            self.process.send_signal(SIGHUP)
            # Use transport.close() because await process.wait() deadlocks
            self.process._transport.close()  # type: ignore
        except ProcessLookupError:
            pass

    @property
    def input_stream(self) -> asyncio.StreamWriter:
        assert self.process is not None, "process not running"
        return self.process.stdin  # type: ignore

    @property
    def output_stream(self) -> asyncio.StreamReader:
        assert self.process is not None, "process not running"
        return self.process.stdout  # type: ignore
