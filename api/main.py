from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

class FormData(BaseModel):
    name: str
    email: str

@app.post("/submit")
async def submit_form(data: FormData):
    print(f"Received data: {data}")
    return {"message": "Data received successfully"}


class AuthData(BaseModel):
    mode: str  # 'login' or 'signup'
    email: str
    password: str
    name: Optional[str] = None


@app.post("/auth")
async def auth(data: AuthData):
    mode = data.mode.lower().strip()
    if mode not in {"login", "signup"}:
        raise HTTPException(status_code=400, detail="Invalid mode. Use 'login' or 'signup'.")

    # Placeholder logic to be implemented later
    if mode == "login":
        return {"message": "Login placeholder", "email": data.email}
    else:
        return {"message": "Signup placeholder", "email": data.email, "name": data.name}
