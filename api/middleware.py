import logging
from fastapi import Request

logger = logging.getLogger("api3")


async def log_requests(request: Request, call_next):
    """Simple request logging middleware."""
    logger.info(f"{request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"-> {response.status_code} {request.method} {request.url.path}")
        return response
    except Exception as e:
        logger.exception(f"Unhandled error for {request.method} {request.url.path}: {e}")
        raise

