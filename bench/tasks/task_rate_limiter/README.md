# Task: Fix Rate Limiter

The `allow()` method uses `>` instead of `>=` when checking the call count, allowing one extra call through.

Fix the comparison operator. Do NOT modify the test file.