from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    app.include_router(api_router)
    return app
