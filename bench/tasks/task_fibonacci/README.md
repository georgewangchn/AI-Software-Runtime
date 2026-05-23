# Task: Fix Fibonacci Memoization

The `fib()` function creates a new empty cache on every call, so memoization never works. The cache must persist across recursive calls.

Fix the cache so it is shared across all recursive calls within a single `fib(n)` invocation.