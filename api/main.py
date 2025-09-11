from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class FormData(BaseModel):
    name: str
    email: str

@app.post("/api/submit")
async def submit_form(data: FormData):
    print(f"Received data: {data}")
    return {"message": "Data received successfully"}
