from fastapi import FastAPI, Request
import logging
from .middleware import log_requests
from .routes.user import router as user_router
from .routes.admin import router as admin_router


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api3")

app = FastAPI()


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    return await log_requests(request, call_next)


# Mount admin first to avoid catch-all collisions
app.include_router(admin_router)
app.include_router(user_router)
