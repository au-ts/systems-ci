#!/usr/bin/env python3
# Copyright 2026, UNSW
# SPDX-License-Identifier: BSD-2-Clause

from __future__ import annotations
from abc import abstractmethod
from collections.abc import Hashable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .backends import HardwareBackend


# expects eq, ordering, hashing... but we unfortunately cannot make these
# @abstractmethod as this creates inheritance issues with dataclasses, which
# was why `abc.update_abstractmethods` was added in Python 3.10.
# we also want a 'no_output_timeout_s' property, but we cannot check this.
class TestCase(Protocol):
    @abstractmethod
    async def run(self, HardwareBackend) -> None: ...

    @abstractmethod
    def pretty_name(self) -> str: ...

    @abstractmethod
    def loader_img(self) -> Path: ...

    @abstractmethod
    def backend(self, loader_img: Path) -> HardwareBackend: ...

    """Timeout in seconds for no output watchdog"""
    no_output_timeout_s: int

    @abstractmethod
    def log_file_path(self, logs_dir: Path, now: datetime) -> Path: ...
