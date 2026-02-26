from fastapi import APIRouter

from aventi_backend.api.routes import events, favorites, feed, health, internal, me, membership, swipes

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(me.router, prefix="/v1/me", tags=["me"])
api_router.include_router(feed.router, prefix="/v1", tags=["feed"])
api_router.include_router(swipes.router, prefix="/v1", tags=["swipes"])
api_router.include_router(favorites.router, prefix="/v1", tags=["favorites"])
api_router.include_router(events.router, prefix="/v1", tags=["events"])
api_router.include_router(membership.router, prefix="/v1", tags=["membership"])
api_router.include_router(internal.router, prefix="/internal", tags=["internal"])
