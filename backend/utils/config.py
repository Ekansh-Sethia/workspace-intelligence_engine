from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Workspace Intelligence Engine"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "postgresql://wie_user:wie_password@localhost:5432/wie_db"


    # Redis / Tasks
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    RUN_CELERY_IN_PROCESS: bool = True
    
    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    
    # Auth
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30 # 30 minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7 # 7 days

    # LLM Gateway — Phase 9
    GEMINI_API_KEY: str | None = None
    # Primary: Groq / Llama (free tier: generous rate limits, very fast inference)
    GROQ_API_KEY: str = ""

    # Backend / System config
    FRONTEND_URL: str = "http://localhost:3000"

    # RAG retrieval config
    RAG_TOP_K: int = 5                  # Number of chunks to retrieve per query
    RAG_HISTORY_TURNS: int = 6          # Number of past turns to include in context (3 user + 3 assistant)
    
    # Models
    LLM_PRIMARY_MODEL: str = "gemini/gemini-3.6-flash"
    LLM_FALLBACK_MODEL: str = "groq/llama-3.1-8b-instant"
    LLM_FAST_MODEL: str = "groq/llama-3.3-70b-versatile"
    LLM_VISION_MODEL: str = "llama-3.2-11b-vision-preview"

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()
