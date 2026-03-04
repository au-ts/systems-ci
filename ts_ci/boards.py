# Copyright 2026, UNSW
# SPDX-License-Identifier: BSD-2-Clause

from typing import Any

# The ordering in these lists defines an implicit ordering of which boards
# to use for CI preferentially, though all will eventually be tried.
MACHINE_QUEUE_BOARDS: dict[str, list[str]] = {
    "hifive_p550": ["p550a"],
    "serengeti": ["serengeti1", "serengeti2"],
    "imx8mm_evk": ["imx8mm"],
    "imx8mp_iotgate": ["iotgate1"],
    "imx8mq_evk": ["imx8mq", "imx8mq2"],
    "maaxboard": ["maaxboard1", "maaxboard2"],
    "odroidc2": ["odroidc2"],
    "odroidc4": ["odroidc4_1", "odroidc4_2"],
    "star64": ["star64"],
    "zcu102": ["zcu102", "zcu102_2"],
    "rpi4b_1gb": ["pi4B"],
}

MACHINE_QUEUE_BOARD_OPTIONS: dict[str, dict[str, Any]] = {
    "serengeti": dict(uboot_image_started=b"Starting kernel ..."),
    "star64": dict(uboot_image_started=b"Starting kernel ..."),
    "hifive_p550": dict(uboot_image_started=b"Starting kernel ..."),
}
