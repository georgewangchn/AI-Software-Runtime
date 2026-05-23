# Task: Fix CLI Argument Parser

Two bugs in argument parsing:

1. **Negative count not rejected**: `--count -1` should return None (invalid), but it doesn't.
2. **Zero count rejected**: `--count 0` should be accepted, but it triggers the negative check.
3. **Output key missing**: When `--output` is provided, `process()` should include an "output" key in the result dict.

Fix all bugs so tests pass. Do NOT modify the test file.
