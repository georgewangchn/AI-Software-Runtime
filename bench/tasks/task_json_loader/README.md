# Task: Fix JSON Config Loader

The `validate_config()` function has bugs in its validation logic:

1. When `port` key is missing from config, it returns `True` instead of `False`
2. When `port` is `None`, it returns `True` instead of `False`
3. When `port` is a string (not int), it returns `True` instead of `False`

Fix `validate_config()` so all tests pass. Do NOT modify the test file.
