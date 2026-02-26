import uvicorn

from aventi_backend.app import create_app
from aventi_backend.core.settings import get_settings

app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "aventi_backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.env == "development",
    )


if __name__ == "__main__":
    main()
