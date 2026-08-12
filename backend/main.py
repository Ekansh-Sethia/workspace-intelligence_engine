from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from utils.config import settings
from utils.exceptions import WIEException, wie_exception_handler, global_exception_handler
from api.health import router as health_router
from authentication.router import router as auth_router
from workspaces.router import router as workspaces_router
from chat.router import router as chat_router
from core.qdrant import init_qdrant
from utils.logger import logger
# Import chat models so Alembic metadata includes them
import chat.models  # noqa: F401

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before serving requests."""
    logger.info("Application startup: initialising Qdrant...")
    init_qdrant()
    logger.info("Application startup complete.")
    yield
    logger.info("Application shutdown.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    # Set all CORS enabled origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception Handlers
    app.add_exception_handler(WIEException, wie_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    # Routers
    app.include_router(health_router, prefix=settings.API_V1_STR)
    app.include_router(auth_router, prefix=settings.API_V1_STR)
    app.include_router(workspaces_router, prefix=settings.API_V1_STR)
    app.include_router(chat_router, prefix=settings.API_V1_STR)
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {"message": f"Welcome to {settings.PROJECT_NAME} API"}

    return app

app = create_app()
