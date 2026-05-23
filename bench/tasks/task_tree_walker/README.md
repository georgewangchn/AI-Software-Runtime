# Task: Fix Tree Walker

The `find_value()` function has an infinite recursion bug: after checking all children, it calls `find_value(root, target)` instead of returning None.

Fix the fallthrough case. Do NOT modify the test file.