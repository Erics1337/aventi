from mangum import Mangum
import structlog

from aventi_backend.core.logging import configure_logging
from aventi_backend.core.settings import get_settings
from aventi_backend.main import app

# Initialize logging early during cold start
configure_logging(get_settings().log_level)

logger = structlog.get_logger(__name__)
logger.info("Initializing Mangum adapter for FastAPI...")

# Wrap FastAPI into Mangum adapter
handler = Mangum(app, api_gateway_base_path=None, text_mime_types=[
    "text/", "application/json", "application/xml"
])
