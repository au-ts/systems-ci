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

## Style

The CI runs a style check on any changed files and new files added in each
GitHub pull request.

### Python code

For helper scripts and the metaprograms (`meta.py`) which are written in Python,
we use [black](https://black.readthedocs.io/en/stable/).

Running `black . --required-version 25` in the root of the repository or on a
specific directory/file will run the Python style check.

Note that currently we target the 2025 styling of black.
