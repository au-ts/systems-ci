# ts_ci

This folder contains a set of python scripts that can be used to build a CI
system that has the following requirements:

- Runnable locally outside of any specific CI 'actions runner' host (i.e. GitHub)
- Handles a limited number of hardware resources, including 'locking' of boards
  such as in the [seL4 machine queue helper scripts](https://github.com/seL4/machine_queue).
- Handles board failures.
- Interacting testing over serial.
- Produces log files for all actions for later viewing.

We target Python 3.9 for compatibility with our macOS runner.

## Supporting a new project

The goal of `ts_ci` is to provide the common framework code for various au-ts
systems. Because the requirements and layout of our various repositories (e.g.
sDDF vs libvmm vs LionsOS) are different, we do not wish to hardcode what
constitutes a "test case" and the properties it has, but we want to have a
relatively uniform way of running examples and filtering subsets of examples.

To execute the tests, the library expects the `ts_ci.execute_tests()` function
to be called. This takes:

 -  `tests`: `list[TestCase]`, an array of classes which conform to the `TestCase`
    protocol. One generally declares a `class TestConfig` that implements the
    `TestCase` protocol, which has the ability to create a `.backend`, a `.pretty_name`,
    a `.loader_img`, a `.run`, and a `.log_file_path`. This is used by the
    test runner to run each individual test.

 -  `args`, an `argparse.Namespace` generated from `parser.parse_args()`; this
    is used for the common CLI arguments added by `add_runner_arguments()`.

 -  `test_case_summary`, a helper function used to format the examples when
    printing a summary of succeeded/failed/skipped test cases.


```py
    parser = argparse.ArgumentParser()

    # etc
    filters = parser.add_argument_group(title="filters")
    filters.add_argument(...)

    ts_ci.add_runner_arguments(parser)

    args = parser.parse_args()
    filter_args = argparse.Namespace(**{a.dest: getattr(args, a.dest) for a in filters._group_actions})
    tests = subset_test_cases(tests, filter_args)
    tests = ts_ci.apply_runner_arguments(parser, args, tests, test_case_summary)

    ts_ci.execute_tests(tests, args, test_case_summary)
```

The `add_runner_arguments()` function adds the general arguments handled by the
library, for controlling the behaviour of the test runner. It is complemented
then by `apply_runner_arguments()` which checks / tests these arguments.


Semi-complete example below. For a more detailed example, see [sDDF ci/common.py](
https://github.com/au-ts/sddf/blob/main/ci/common.py). Note that we have some
common conventions across the Trustworthy Systems libraries:

 -  As one sees above and below, we have a `subset_test_cases` function, and we add
    filter arguments. We add several items in a filter subgroup which we use
    to subset the test case array.

 -  The use of a test 'matrix', discussed below.

```py
from ts_ci import (
    add_runner_arguments,
    apply_runner_arguments,
    execute_tests,
    ArgparseActionList,
    HardwareBackend,
    MachineQueueBackend,
    MACHINE_QUEUE_BOARDS,
    MACHINE_QUEUE_BOARD_OPTIONS,
    TestCase,
)

def backend_fn(
    test_config: TestCase,
    loader_img: Path,
) -> HardwareBackend:

    mq_boards: list[str] = MACHINE_QUEUE_BOARDS[test_config.board]
    options = MACHINE_QUEUE_BOARD_OPTIONS.get(test_config.board, {})
    return MachineQueueBackend(loader_img.resolve(), mq_boards, **options)


TestFunction = Callable[[HardwareBackend, "TestConfig"], Awaitable[None]]
BackendFunction = Callable[["TestConfig", Path], HardwareBackend]


# Implements 'TestCase' protocol
@dataclass(order=True, frozen=True)
class TestConfig(TestCase):
    example: str
    board: str

    test_fn: TestFunction
    backend_fn: BackendFunction
    no_output_timeout_s: int

    def pretty_name(self) -> str:
        return f"{self.example} on {self.board}"

    def backend(self, loader_img: Path) -> HardwareBackend:
        return self.backend_fn(self, loader_img)

    def loader_img(self) -> Path:
        return Path("build") / self.example / self.board / "loader.img"

    async def run(self, backend: HardwareBackend) -> None:
        await self.test_fn(backend, self)

    def log_file_path(self, logs_dir: Path, now: datetime) -> Path:
        return logs_dir / self.example / self.board / f"{now.strftime('%Y-%m-%d_%H.%M.%S')}.log"


def test_case_summary(tests: list[TestConfig]):
    if len(tests) == 0:
        return "   (none)"

    lines = []
    for example, subtests in itertools.groupby(tests, key=lambda c: c.example):
        lines.append(f"--- Example: {example} ---")

        for board, group in itertools.groupby(subtests, key=lambda c: c.board):
            lines.append(" - {}".format(board))

    return "\n".join(lines)


def subset_test_cases(
    tests: list[TestConfig], filters: argparse.Namespace
) -> list[TestConfig]:
    def filter_check(test: TestConfig):
        return all(
            [
                (test.example in filters.examples),
                (test.board in filters.boards),
            ]
        )

    return list(sorted(set(filter(filter_check, tests))))


def run_tests(tests: list[TestConfig]) -> None:
    parser = argparse.ArgumentParser(description="Run examples")

    filters = parser.add_argument_group(title="filters")
    filters.add_argument("--examples", default={test.example for test in tests}, action=ArgparseActionList)
    filters.add_argument("--boards", default={test.board for test in tests}, action=ArgparseActionList)

    add_runner_arguments(parser)

    args = parser.parse_args()
    filter_args = argparse.Namespace(**{a.dest: getattr(args, a.dest) for a in filters._group_actions})
    tests = subset_test_cases(tests, filter_args)
    tests = apply_runner_arguments(parser, args, tests, test_case_summary)

    execute_tests(tests, args, test_case_summary)
```

Another common pattern we use throughout our repositories, which is not enforced
by this library, is that we have a `matrix.py` that is able to generate the
list of `TestCase`. `ts_ci` provides a `matrix_product` which does a "Cartesian product"
of the provided arguments. On top of this we build some kind of `generate_example_test_cases()`
helper, that is able to filter out as needed the tests we don't/can't run
from the matrix. Here is a snippet as seen in sDDF:

```py
def generate_example_test_cases(
    example: str,
    example_matrix: _ExampleMatrixType,
    test_fn: TestFunction,
    backend_fn: BackendFunction,
    no_output_timeout_s: int,
) -> list[TestConfig]:
    def listify(s: str | Sequence[str]) -> Sequence[str]:
        if isinstance(s, str):
            return [s]
        else:
            return s

    matrix = set(
        matrix_product(
            TestConfig,
            example=[example],
            board=example_matrix["boards"],
            config=example_matrix["configs"],
            build_system=example_matrix["build_systems"],
            test_fn=[test_fn],
            backend_fn=[backend_fn],
            no_output_timeout_s=[no_output_timeout_s],
        )
    )

    for exclude in example_matrix["tests_exclude"]:
        to_exclude = set(
            matrix_product(
                TestConfig,
                example=[example],
                board=listify(exclude.get("board", example_matrix["boards"])),
                config=listify(exclude.get("config", example_matrix["configs"])),
                build_system=listify(
                    exclude.get("build_system", example_matrix["build_systems"])
                ),
                test_fn=[test_fn],
                backend_fn=[backend_fn],
                no_output_timeout_s=[no_output_timeout_s],
            )
        )
        matrix -= to_exclude

    return list(matrix)

EXAMPLES: dict[str, _ExampleMatrixType] = {
    "blk": {
        "configs": ["debug", "release"],
        "build_systems": ["make", "zig"],
        "boards": [
            "maaxboard",
            "qemu_virt_aarch64",
            "qemu_virt_riscv64",
            "x86_64_generic",
        ],
        "tests_exclude": [
            { "config": "release" },
        ],
    },
}
```

We also have some 'common' code that appears at the end of each test file.
This allows us to have a central set for all of the configs of what to run
and what to build, but also to run each test case individually. This is not a
requirement of the `ts_ci` but is our convention in our users of this library.

```py
# export
TEST_CASES = matrix.generate_example_test_cases(
    "blk",
    matrix.EXAMPLES["blk"],
    test_fn=test,
    backend_fn=common.backend_fn,
    no_output_timeout_s=matrix.NO_OUTPUT_DEFAULT_TIMEOUT_S,
)


if __name__ == "__main__":
    common.run_tests(TEST_CASES)
```

We also provide two other helper files: `build.py` and `run.py`.

 -  `build.py` is a thin wrapper over both the `matrix.EXAMPLES` and the build system,
    that is, it runs `make` or `zig` (etc) for each of the examples in the matrix.
    Below is an example. The definition of `build` will be specific to the project.

    ```py
    if __name__ == "__main__":
        parser = argparse.ArgumentParser(description=__doc__)

        parser.add_argument("microkit_sdk")
        parser.add_argument("num_jobs", nargs="?", type=int, default=os.cpu_count())
        parser.add_argument(
            "--examples",
            default=set(matrix.EXAMPLES.keys()),
            action=ArgparseActionList,
        )
        parser.add_argument(
            "--no-clean",
            action="store_true",
            help="Do not remove any pre-existing CI build directory before building",
        )

        args = parser.parse_args()

        for example_name, options in matrix.EXAMPLES.items():
            if example_name not in args.examples:
                continue

            matrix = set(
                matrix_product(
                    common.TestConfig,
                    example=[example_name],
                    board=options["boards"],
                    config=options["configs"],
                    build_system=options["build_systems"],
                    test_fn=[None],
                    backend_fn=[None],
                    no_output_timeout_s=[None],
                )
            )
            for test_config in matrix:
                build(args, test_config)

    ```

 -  `run.py` is similar, but collates all the test scripts' `TEST_CASES` and
    combines them to call `common.run_tests` on all of them, such that all the
    examples are combined. This usually iterates over a folder and imports them:

    ```py
    from ts_ci import log

    sys.path.insert(1, Path(__file__).parents[1].as_posix())
    from ci.common import run_tests, TestConfig

    EXAMPLES_DIR = Path(__file__).parent / "examples"
    EXAMPLES_LIST = sorted(
        [
            e.removesuffix(".py")
            for e in os.listdir(EXAMPLES_DIR)
            if (e.endswith(".py") and e != "__init__.py")
        ]
    )

    if __name__ == "__main__":
        examples_list = sorted(set(EXAMPLES_LIST))
        if len(examples_list) == 0:
            log.error("no examples found")
            exit(1)

        tests: list[TestConfig] = []

        for example in examples_list:
            mod = importlib.import_module(f"ci.examples.{example}")
            tests.extend(mod.TEST_CASES)

        run_tests(tests)
    ```

## Internal Architecture

The exports of the `ts_ci` package can be split into three categories:

1.  Hardware Backends. This is a base class which defines a `start()`, `stop()`
    method which controls booting of the hardware (or the simulation process, etc).
    It also defines two properties, `input_stream` and `output_stream` which
    is the `StreamReader` and `StreamWriter` for serial-based process communication.

    ```py
    class HardwareBackend(ABC):
        @abstractmethod
        async def start(self):
            """Start the hardware and wait for it to have booted"""

        @abstractmethod
        async def stop(self):
            """Stop the hardware"""

        @property
        @abstractmethod
        def output_stream(self) -> StreamReader: ...

        @property
        @abstractmethod
        def input_stream(self) -> StreamWriter: ...

    ```

    We have a few implementations of this HardwareBackend that are common:

     -  The `QemuBackend`, which handles starting a QEMU process and stopping it.
        The actual arguments are up to the responsibility of each user of this
        library; often we set different arguments per examples.

     -  The `MachineQueueBackend`, which handles interacting with Trustworthy
        System's 'machine queue' which is a lock-based system for interacting
        with physical boards.

     -  The `TtyBackend`, which is rarely used, but always one to connect
        over a local serial device to a board. It does not handle restarting
        the board, and requires human interaction.

    We provide following helper functions for performing tests:

     -  `send_input(backend, bytes)` Sends a string to the input of the board
        which is useful for interacting over serial.

     -  `wait_for_output(backend, bytes, [timeout])` This allows arbitrary output
        from the board until it sees a match for the given string. If it does
        not see the output within the timeout it will raise a test failure.

     -  `expect_output(backend, bytes)` This is similar to `wait_for_output`,
        but it instead expects that the *next* seen bytes are exactly as expected.

2.  Machine Queue common information. This consists of the `MACHINE_QUEUE_BOARDS`
    and `MACHINE_QUEUE_BOARD_OPTIONS`, which is useful for constructing the
    `MachineQueueBackend` type: specifically, so that we don't need to duplicate
    across many repositories any updates to which boards exist in our hardware
    CI room.

3.  The test scheduler. This is really the most important part of this repository;
    the key motivation for writing our own test runner is being able to handle
    'locks', that is, that we might have hardware boards in-use, and we should
    instead schedule another test in its place. That is, it internally keeps
    a queue of tests to run, and upon encountering a locked board a backend
    raises `TestRetryException` which puts it back in the runner queue; and
    tests are retried after a certain delay if there are no runnable tests.

    The pseudocode would look something like this:

    ```py

    to_run: queue
    next_to_run: queue
    passed/failed: queue

    while retry_count < 5:

        for test in to_run:
            run test
            if needs_retry:
                add to next_to_run
            else:
                add to passed/failed

        wait 'retry delay' time
        retry_count += 1

    ```

    Here in the runner we also manipulate test stdout so that they are recorded
    in log files.

There exists a few other miscellaneous helpers:

 -  `matrix_product` which takes a dataclass constructor and each field as an array,
    and creates the cartesian product.

 -  `ArgparseActionList` which from a list of values generates command line
    arguments `--<name> {value1,value2,...}` and `--exclude-<name> {value1, value2}`
    which is useful for generating the filter arguments.

 -  `TeeOutput` used internally for placing output from tests to stdout and to
    a file.

 -  `log`, which is a function that is useful for formatting log outputs like
    `CI|INFO` during the test for informative messages.
