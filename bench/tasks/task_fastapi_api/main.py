from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

users_db = [
    {"id": 1, "name": "Alice", "email": "alice@example.com"},
    {"id": 2, "name": "Bob", "email": "bob@example.com"},
]
_next_id = 3

class UserCreate(BaseModel):
    name: str
    email: str

@app.get("/users/search")
def search_users(q: Optional[str] = None):
    if not q:
        return []
    return [u for u in users_db if q.lower() in u["name"].lower()]

@app.get("/users/{user_id}")
def get_user(user_id: int):
    for user in users_db:
        if user["id"] == user_id:
            return {"id": user["id"], "name": user["name"]}
    raise HTTPException(status_code=404, detail="User not found")

@app.post("/users", status_code=201)
def create_user(user: UserCreate):
    global _next_id
    new_user = {"id": _next_id, "name": user.name, "email": user.email}
    users_db.append(new_user)
    _next_id += 1
    return new_user
