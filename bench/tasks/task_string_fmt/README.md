# Task: Fix String Formatter

The `truncate()` function adds '...' but doesn't account for the ellipsis length when computing the truncation point. Result can exceed max_len.

Fix truncate so result length including '...' never exceeds max_len.