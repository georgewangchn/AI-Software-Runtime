# Task: Fix Date Parser

The `is_leap_year()` function only checks divisibility by 4, missing the century rule (years divisible by 100 are NOT leap years unless also divisible by 400). So 1900 is incorrectly treated as a leap year.

Fix is_leap_year. Do NOT modify the test file.