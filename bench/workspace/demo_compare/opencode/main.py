from typing import Optional
from fastapi import FastAPI, HTTPException
from models import User, UserCreate

app = FastAPI()

users_db = [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"},
]

_next_id = 3


@app.get("/users/search")
def search_users(q: Optional[str] = None):
    if not q:
        return []
    # Sanitize query: remove non-printable and whitespace-only input
    sanitized_q = ''.join(c for c in q if c.isprintable()).strip()
    if not sanitized_q:
        return []
    return [u for u in users_db if sanitized_q.lower() in u["name"].lower()]


@app.get("/users/{user_id}")
def get_user(user_id: int):
    for user in users_db:
        if user["id"] == user_id:
            return {"id": user["id"], "name": user["name"], "email": user["email"]}
    raise HTTPException(status_code=404, detail="User not found")


@app.post("/users", status_code=201)
def create_user(user: UserCreate):
    global _next_id
    # Check for duplicate email
    for existing_user in users_db:
        if existing_user["email"] == user.email:
            raise HTTPException(status_code=409, detail="Email already exists")
    
    new_user = {"id": _next_id, "name": user.name, "email": user.email}
    users_db.append(new_user)
    _next_id += 1
    return new_user
