#!/usr/bin/env python3
# Copyright 2026, UNSW
# SPDX-License-Identifier: BSD-2-Clause

from __future__ import annotations
from abc import abstractmethod, ABC
from collections import abc
from dataclasses import dataclass
from datetime import datetime
from typing import Self
from pathlib import Path

from .backends import HardwareBackend


# expects eq, ordering, hashing...
class TestCase(abc.Hashable, ABC):
    @abstractmethod
    async def run(self, HardwareBackend) -> None: ...

    @abstractmethod
    def pretty_name(self) -> str: ...

    @abstractmethod
    def loader_img(self) -> Path: ...

    @abstractmethod
    def backend(self, loader_img: Path) -> HardwareBackend: ...

    no_output_timeout_s: int
    # property: no_output_timeout_s: int
    # abstractproperties are broken
    # Timeout in seconds for no output watchdog"""

    @abstractmethod
    def log_file_path(self, logs_dir: Path, now: datetime) -> Path: ...

    @abstractmethod
    def __lt__(self, other: Self) -> bool: ...
