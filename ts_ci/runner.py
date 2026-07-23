#!/usr/bin/env python3
# Copyright 2025, UNSW
# SPDX-License-Identifier: BSD-2-Clause

"""
Runner (CLI) script for running the hardware tests automagically.
This includes automatic, interactive tests using our "Machine Queue" or within
QEMU.
"""

import argparse
import asyncio
from collections.abc import Awaitable, Callable
import contextlib
from datetime import datetime
import itertools
from pathlib import Path
import traceback
from typing import Any, ContextManager, Coroutine, Literal, Optional, Tuple

from . import log
from .backends import (
    HardwareBackend,
    TestRetryException,
    TestFailureException,
    reset_terminal,
    log_output_to_file,
    TeeOut,
    OUTPUT,
)
from .interface import TestCase
from .stream_watchdog import StreamWatchdog

TestCaseSummaryFunction = Callable[[list[TestCase]], str]


def matrix_product(dataclass, **items):
    assert set(items.keys()) <= set(
        dataclass.__dataclass_fields__.keys()
    ), "keys subset of config fields"

    return [
        dataclass(**dict(zip(items.keys(), fields)))
        for fields in itertools.product(*items.values())
    ]


class ArgparseActionList(argparse.Action):
    def __init__(
        self,
        option_strings: list[str],
        dest: str,
        default=None,
    ):
        _option_strings = []
        for option_string in option_strings:
            _option_strings.append(option_string)

            if option_string.startswith("--"):
                option_string = "--exclude-" + option_string[2:]
                _option_strings.append(option_string)

        if not isinstance(default, set):
            raise TypeError(f"default must be a set, got {type(default)}")

        super().__init__(
            option_strings=_option_strings,
            dest=dest,
            default=default,
            # can't use choices as this restricts to single items
            # TODO oops: no verification that the argument is valid
            #            without choices....
            metavar="{" + ",".join(sorted(default)) + "}",
        )

        self.kind: Literal["additive", "subtractive"] | None = None

    def __call__(self, parser, namespace, values: str, option_string: str):  # type: ignore
        values_set = set(values.split(","))
        if option_string and option_string.startswith("--exclude"):
            kind: Literal["additive", "subtractive"] = "subtractive"
            values_set = self.default - values_set
        else:
            kind = "additive"

        if self.kind is None:
            self.kind = kind

        if self.kind != kind:
            raise argparse.ArgumentError(
                self,
                "cannot use exclude and non-exclude flags together for {}".format(
                    option_string
                ),
            )

        setattr(namespace, self.dest, values_set)


ResultKind = Literal["pass", "fail", "not_run", "retry", "interrupted"]


async def _run_test_case(
    test: TestCase,
    logs_dir: Optional[Path] = None,
    loader_img_override: Optional[Path] = None,
) -> ResultKind:

    if logs_dir:
        log_file = test.log_file_path(logs_dir, datetime.now())
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file_cm: ContextManager = log_output_to_file(log_file)
    else:
        log_file_cm = contextlib.nullcontext()

    # Please be aware whilst modifying this loop of Python asyncio issues
    # gh-103847, bpo-39622, gh-32105, gh-119710 and other issues filed in CPython,
    # with deadlocks in the subprocess modules and cancellation safety issues.
    with log_file_cm:

        try:
            try:
                loader_img = loader_img_override or test.loader_img()
                backend = test.backend(loader_img)
            except Exception as e:
                log.error(f"Backend creation failed: {e}")
                return "fail"

            async with StreamWatchdog(test.no_output_timeout_s, OUTPUT):
                try:
                    await backend.start()
                    await test.run(backend)
                except EOFError as e:
                    raise TestFailureException(
                        "EOF when reading from backend stream"
                    ) from e
                except asyncio.IncompleteReadError as e:
                    raise TestFailureException(
                        f"EOF when reading from backend stream: {e}"
                    ) from e
                except (TimeoutError, asyncio.TimeoutError) as e:
                    raise TestFailureException("timeout") from e
                except asyncio.CancelledError:
                    log.info("cancelling tests...")
                    raise

                finally:
                    reset_terminal()
                    await backend.stop()

        except TestFailureException as e:
            log.error(f"Test failed: {e}")
            return "fail"
        except TestRetryException as e:
            log.info(f"Retrying later due to transient failure: {e}")
            return "retry"
        except (asyncio.CancelledError, KeyboardInterrupt):
            log.info("Tests cancelled (SIGINT)")
            return "interrupted"
        except Exception as e:
            log.error(f"Test failed (internal exception):\n{traceback.format_exc()}")
            raise e

        log.info(f"Test passed")
        return "pass"


def add_runner_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--single",
        action="store_true",
        help="only run the single test selected, failing if the filters applied select more than one test",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="instead of running tests, show what would have been run",
    )
    parser.add_argument(
        "--fast-fail",
        action="store_true",
        help="fail on first test failure",
    )
    parser.add_argument(
        "--override-backend",
        action="store_true",
        help="force the use of a specific backend to run the test. requires --single",
    )
    parser.add_argument(
        "--override-image",
        type=Path,
        help="force the use of a specific loader.img file to run the test. requires --single",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=Path("ci_logs"),
        help="save output to a log directory",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=15,
        help=(
            "number of times to retry tests due to transient failures (e.g. lock failures). "
            "prefer increasing this over the delay between retries"
        ),
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=60,
        help=(
            "time (seconds) to delay between transient failure retries. this is between ALL tests, not individual ones. "
            "think of this as the polling delay between checking locks"
        ),
    )


def apply_runner_arguments(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    tests: list[TestCase],
    test_case_summary_fn: TestCaseSummaryFunction,
) -> list[TestCase]:
    if len(tests) == 0:
        parser.error("applied filters result in zero selected tests")

    if args.single and len(tests) != 1:
        parser.error(
            "requested --single but applied filters generated multiple cases: \n"
            + test_case_summary_fn(tests)
        )

    if loader_img := args.override_image:
        if not args.single:
            parser.error("requested --override-image but --single not specified")

        assert Path(loader_img).exists(), "--override-image path does not exist"

        assert len(tests) == 1, "checked earlier"

    if args.override_backend:
        if not args.single:
            parser.error("requested --override-backend but --single not specified")

        assert False, "TODO"

    if args.dry_run:
        print("Would run the following test cases:")
        print(test_case_summary_fn(tests))
        quit(0)

    if not args.override_image:
        for test in tests:
            loader_img = test.loader_img()
            assert loader_img.exists(), f"loader image file {loader_img} does not exist"

    return tests


async def execute_tests_async(
    tests: list[TestCase],
    args: argparse.Namespace,
    test_case_summary_fn: TestCaseSummaryFunction,
):
    assert len(tests) > 0, "Test list is empty."

    test_results: dict[TestCase, ResultKind] = {}
    was_sigint = False

    RETRIES = 1 if args.fast_fail else args.retry_count

    try:
        for retry in range(RETRIES):
            if was_sigint:
                break

            if retry != 0:
                log.info(
                    f"Waiting for {args.retry_delay}s and then retrying round {retry + 1}/{RETRIES}"
                )
                await asyncio.sleep(args.retry_delay)

            for test_case in tests:
                if test_results.get(test_case, "retry") != "retry":
                    # skip any tests that are completed
                    continue

                fmt = test_case.pretty_name()
                log.group_start("Running " + fmt)
                result = await _run_test_case(
                    test_case,
                    args.logs_dir,
                    args.override_image,
                )
                log.group_end("Finished running " + fmt)

                test_results[test_case] = result

                if result == "interrupted":
                    was_sigint = True
                    break

    except (asyncio.CancelledError, KeyboardInterrupt):
        was_sigint = True

    finally:
        passing, failing, retry_failures, not_run = [], [], [], []
        for test_case in tests:
            result = test_results.get(test_case, "not_run")
            if result == "pass":
                passing.append(test_case)
            elif result == "fail" or result == "interrupted":
                failing.append(test_case)
            elif result == "retry":
                retry_failures.append(test_case)
            elif result == "not_run":
                not_run.append(test_case)
            else:
                assert False, "impossible"

        print("==== Passing ====")
        print(test_case_summary_fn(passing))
        print("==== Failed =====")
        print(test_case_summary_fn(failing))
        if len(not_run) != 0:
            print("===== Cancelled (not run) =====")
            print(test_case_summary_fn(not_run))
        if len(retry_failures) != 0:
            print("===== Transient failures remaining after multiple retries ====")
            print(test_case_summary_fn(retry_failures))

    if was_sigint:
        quit(130)

    if len(passing) != len(tests):
        quit(1)


def execute_tests(
    tests: list[TestCase],
    args: argparse.Namespace,
    test_case_summary_fn: TestCaseSummaryFunction,
):
    asyncio.run(execute_tests_async(tests, args, test_case_summary_fn))
