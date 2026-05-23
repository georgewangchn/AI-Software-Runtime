# Task: Fix Retry Decorator

The `retry()` decorator applies `time.sleep(delay)` even on the last attempt, just before re-raising the exception. This causes unnecessary waiting.

Fix: move `time.sleep(delay)` so it only runs when NOT on the last attempt (after the raise check).

Do NOT modify the test file.
