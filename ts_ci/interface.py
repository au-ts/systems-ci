#!/usr/bin/env python3
# Copyright 2026, UNSW
# SPDX-License-Identifier: BSD-2-Clause

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Awaitable
from pathlib import Path

from .backends import HardwareBackend


@dataclass(order=True, frozen=True)
class TestConfig:
    example: str
    board: str
    config: str
    build_system: str
    metadata: TestMetadata

    def is_qemu(self):
        # TODO: x86_64_generic assumes QEMU for the moment.
        return self.board.startswith("qemu") or self.board == "x86_64_generic"


TestFunction = Callable[[HardwareBackend, TestConfig], Awaitable[None]]
BackendFunction = Callable[[TestConfig, Path], HardwareBackend]
LoaderImgFunction = Callable[[TestConfig], Path]


@dataclass(order=True, frozen=True)
class TestMetadata:
    test_fn: TestFunction
    backend_fn: BackendFunction
    loader_img_fn: LoaderImgFunction
    no_output_timeout_s: int
