from uuid import uuid4

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aventi_backend.api.router import api_router
from aventi_backend.core.logging import configure_logging
from aventi_backend.core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Aventi API",
        version="0.1.0",
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url="/redoc" if settings.env != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id
        try:
            if settings.env != "test" and request.url.path != "/v1/health":
                from aventi_backend.core.limits import enforce_limit

                # Do not trust a caller-supplied forwarded-for header.
                address = request.client.host if request.client else "unknown"
                await enforce_limit(f"ip:{address}", settings.request_limit_per_minute * 3)
            response = await call_next(request)
        except HTTPException as exc:
            response = JSONResponse(
                status_code=exc.status_code,
                content={"error": {"message": exc.detail, "requestId": request_id}},
                headers=exc.headers,
            )
        except Exception:
            structlog.get_logger().exception("request.failed", request_id=request_id)
            response = JSONResponse(
                status_code=500,
                content={"error": {"message": "Service unavailable", "requestId": request_id}},
            )
        if response.status_code >= 500:
            structlog.get_logger().error(
                "api.server_error", request_id=request_id, status=response.status_code
            )
            if request.url.path.startswith("/v1/membership"):
                structlog.get_logger().error("membership.sync_failed", request_id=request_id)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.detail,
                    "requestId": getattr(request.state, "request_id", None),
                }
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": "Invalid request",
                    "requestId": getattr(request.state, "request_id", None),
                }
            },
        )

    app.include_router(api_router)
    return app
