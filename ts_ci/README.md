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

## Internal Architecture

*TODO: More documentation, especially about the scheduler and Ctrl+C handling*.

### A new test.

Each test file needs to export a minimum of two global variables

- `TEST_MATRIX`, which is a list of `TestConfig` types containing information
  about the different boards and example configuration information.

- `TEST_METADATA`, which contains several function pointers:
    - `test_fn` is an `async def test(backend: HardwareBackend, test_config: TestConfig):`
       that run the test.
       It can raise `TestFailureException` to indicate a test failure, which
       the helper functions `wait_for_output` and `expect_output` will do.

    - `backend_fn` which creates an instance of a `HardwareBackend`, such as
      `QemuBackend` or `MachineQueueBackend` that corresponds with how to
      access specific hardware.

    - `loader_img_fn` which specifies the path to the image that we pass to
      `backend_fn`. It is useful as it allows us to handle the `--override-image`
      argument that allows running a specific example with a custom loader img path.

    - `no_output_timeout_s` an integer representing the number of seconds of
      *no output* from the board that is treated as failure. Any output from the
      board resets the watchdog. This is useful for boot failure detection.

```py

TEST_MATRIX = matrix_product(
    example=["timer"],
    board=["blue board", "green board"],
    config=["debug", "release"],
    build_system=[...],
)

# export
TEST_METADATA = TestMetadata(
    test_fn=test,
    backend_fn=common.backend_fn,
    loader_img_fn=common.loader_img_path,
    no_output_timeout_s=matrix.NO_OUTPUT_DEFAULT_TIMEOUT_S,
)

if __name__ == "__main__":
    run_test(TEST_METADATA, TEST_MATRIX)

```
