#!/usr/bin/env python3
# Copyright 2025, UNSW
# SPDX-License-Identifier: BSD-2-Clause

import os
from datetime import datetime
from signal import SIGINT
import asyncio
from asyncio.subprocess import PIPE, STDOUT
from pathlib import Path
import sys
import shlex

from .. import log
from .base import HardwareBackend
from .common import LockedBoardException, OUTPUT, TestFailureException
from .streams import expect_output, wait_for_output

BOOT_TIMEOUT = 2 * 60  # 2 minutes
# In case we somehow break and don't release the lock automatically.
# TODO: inherit from somewhere else
LOCK_TIMEOUT = 60 * 60  # 60 minutes
# For Github Actions etc.
IS_CI = bool(os.environ.get("CI"))


LAUNCH_UNIQUE_ID = str(datetime.now())


class MachineQueueBackend(HardwareBackend):
    def __init__(
        self,
        image_file: Path,
        boards: list[str],
        *,
        image_started: bytes = b"## Starting application",
    ):
        """
        boards is the list of valid boards used with mq.sh
        """
        self.image_file = image_file
        self.boards = boards
        self.image_started = image_started
        self.chosen_board = None
        self.process = None

        if IS_CI:
            self.job_key = "-".join(
                [
                    "au_ts_ci",
                    os.environ.get("GITHUB_REPOSITORY", "??"),
                    os.environ.get("GITHUB_WORKFLOW", "??"),
                    os.environ.get("GITHUB_RUN_ID", "??"),
                    os.environ.get("GITHUB_JOB", "??"),
                    os.environ.get("INPUT_INDEX", "0"),
                ]
            )
        else:
            self.job_key = (
                f"au_ts_ci (local file: {image_file}, id: {LAUNCH_UNIQUE_ID})"
            )

    async def start(self):
        if len(self.boards) == 0:
            raise TestFailureException("no boards available")

        assert self.chosen_board is None, "start() should only be called once"

        for board in self.boards:
            self.chosen_board = board
            exe_args = [
                # fmt: off
                "mq.sh", "run",
                # no completion text, so we get stdin as soon as possible
                "-c", "",
                # keep the board running after "completion" text
                "-a",
                # only try to acquire once, don't wait for the lock
                "-t", "0",
                # give a unique lock name
                "-k", self.job_key,
                "-f", self.image_file.as_posix(),
                "-s", self.chosen_board,
                # fmt: on
            ]
            log.info(shlex.join(exe_args))
            self.process = await asyncio.create_subprocess_exec(
                *exe_args,
                stdin=PIPE,
                stdout=PIPE,
                stderr=STDOUT,
            )

            try:
                await expect_output(self, f"Acquiring lock for {board}\n".encode())
                await expect_output(self, f"Lock for {board} currently free\n".encode())
                await expect_output(self, b"Lock acquired, we are allowed to run\n")
                break
            except TestFailureException as e:
                stdout, _ = await self.process.communicate()
                OUTPUT.write(stdout)

        else:
            raise LockedBoardException(self.boards)

        # NOTE: This includes the time for the machine queue to retry booting
        #       a few times due to spurious failures that occur.
        async with asyncio.timeout(BOOT_TIMEOUT):
            await wait_for_output(self, self.image_started)

    async def stop(self):
        # Unfortunately, python's asyncio subprocess modules are very broken
        # and don't like killing-a-process and then waiting for it to complete.
        # In this situation, we perform SIGKILL, and then we perform a manual
        # lock cleanup afterwards.
        if self.process is not None:
            try:
                self.process.kill()
                self.process._transport.close()
            except Exception as e:
                log.info(f"Process {self.process!r}")

        await self._release_lock()

    async def _release_lock(self):
        # Do nothing if we have no board.
        if self.chosen_board is None:
            return

        exe_args = [
            # fmt: off
            "mq.sh", "sem",
            "-signal", self.chosen_board,
            "-k", self.job_key,
            # fmt: on
        ]
        log.info(shlex.join(exe_args))
        release_lock = await asyncio.create_subprocess_exec(
            *exe_args,
            stdout=None,  # inherit -> print
            stderr=None,  # inherit -> print
        )

        # Ignore the return code as we unconditionally try to unlock.
        await release_lock.wait()

    @property
    def input_stream(self) -> asyncio.StreamWriter:
        assert self.process is not None, "process not running"
        return self.process.stdin  # type: ignore

    @property
    def output_stream(self) -> asyncio.StreamReader:
        assert self.process is not None, "process not running"
        return self.process.stdout  # type: ignore
