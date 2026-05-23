# Task: Fix FastAPI User API

There are 3 bugs in this FastAPI application:

1. **get_user endpoint** — the `/users/{user_id}` endpoint does NOT return the `email` field. When a user is found, the response should include id, name, AND email.

2. **create_user endpoint** — the POST `/users` endpoint does NOT check for duplicate emails. It should return HTTP 409 when creating a user with an email that already exists.

3. **search_users endpoint** — the `/users/search` endpoint should handle empty queries gracefully.

Fix all bugs so that all 5 tests in test_main.py pass. Do NOT modify the test file.
