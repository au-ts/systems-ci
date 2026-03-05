<!--
    Copyright 2026, UNSW

    SPDX-License-Identifier: BSD-2-Clause
-->

# systems-ci

This repository contains common files used for CI across the Trustworthy Systems
repositories.

For documentation on how to use the CI runner, have a look at [the sDDF documentation](
https://github.com/au-ts/sddf/tree/main/ci). For internal documentation, look at
[the ts_ci folder][ts_ci/README.md].

## Setup

Locally, you can run the below `pip` command to install `ts_ci`.

```sh
$ pip install git+https://github.com/au-ts/systems-ci#subdirectory=ts_ci
```

We provide an `action.yml` which will set up `PYTHONPATH` such that one can
import the `ts_ci` python package.

```yml
    - name: Setup systems-ci
      uses: au-ts/systems-ci@main
```

Alternatively, specify the `path` input and run `source setup.sh` within a
POSIX shell. This is useful for Nix usecases, where the environment is pure.

```yml
      - name: Setup systems-ci
        uses: au-ts/systems-ci@main
        with:
          path: systems-ci
      - name: Build examples
        run: nix develop --ignore-environment -c bash -c 'source systems-ci/setup.sh && echo hello world'
        shell: bash
```

## Style

The CI runs a style check on any changed files and new files added in each
GitHub pull request.

### Python code

For helper scripts and the metaprograms (`meta.py`) which are written in Python,
we use [black](https://black.readthedocs.io/en/stable/).

Running `black . --required-version 25` in the root of the repository or on a
specific directory/file will run the Python style check.

Note that currently we target the 2025 styling of black.
