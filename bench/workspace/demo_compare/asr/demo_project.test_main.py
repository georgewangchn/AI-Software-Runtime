patching file '/var/folders/gm/_jjtdgms1dg2bgkz_4lvyvgm0000gn/T/tmp9ohuvd5u.txt'
from fastapi import FastAPI, HTTPException
from demo_project.models import User, UserCreate

app = FastAPI(title="User Management API")

users_db: dict[int, User] = {
    1: User(id=1, name="Alice", email="alice@example.com"),
    2: User(id=2, name="Bob", email="bob@example.com"),
    3: User(id=3, name="Charlie", email="charlie@example.com"),
}
_next_id = 4


@app.get("/users/search")
async def search_users(q: str | None = None):
    if not q:
        return []
    first_char = q[0]
    results = [u.model_dump() for u in users_db.values() if u.name.startswith(first_char)]
    return results


@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = users_db.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # BUG 1: missing email field — only returns name, test expects name+email
    return {"name": user.name}


@app.post("/users", status_code=201)
async def create_user(user_data: UserCreate):
    global _next_id
    # BUG 3: does not check for duplicate email — allows duplicate users
    new_user = User(id=_next_id, name=user_data.name, email=user_data.email)
    users_db[_next_id] = new_user
    _next_id += 1
    return new_user.model_dump()
