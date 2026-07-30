from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Workspace Intelligence Engine"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "postgresql://wie_user:wie_password@localhost:5432/wie_db"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

    
    # Redis
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    
    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    
    # Auth
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440 # 24 hours

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()
