"""
ReconAI — Configuration
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        """Application settings loaded from environment variables."""

        # App
        APP_NAME: str = "ReconAI"
        APP_VERSION: str = "1.0.0"
        DEBUG: bool = True

        # Database
        DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "sqlite+aiosqlite:///./reconai.db"
        )

        # OpenAI
        OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        OPENAI_MODEL: str = "gpt-4-turbo"
        OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
        EMBEDDING_DIMENSIONS: int = 768

        # Pinecone
        PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
        PINECONE_INDEX_NAME: str = "reconai-transactions"
        PINECONE_ENVIRONMENT: str = "us-east-1"

        # Reconciliation
        EXACT_MATCH_THRESHOLD: float = 1.0
        FUZZY_MATCH_THRESHOLD: float = 0.85
        LEVENSHTEIN_THRESHOLD: float = 0.80
        AMOUNT_TOLERANCE_PERCENT: float = 0.5
        AMOUNT_TOLERANCE_ABSOLUTE: float = 100.0

        # Safety
        AUTO_RESOLVE_MAX_AMOUNT: float = 10000.0
        MAX_BATCH_SIZE: int = 10000
        REQUIRE_HUMAN_APPROVAL_ABOVE: float = 10000.0

        # Server
        HOST: str = "0.0.0.0"
        PORT: int = 5000
        CORS_ORIGINS: list = ["*"]

        class Config:
            env_file = ".env"
            case_sensitive = True

except ImportError:
    # Resilient fallback using standard library
    class Settings:
        APP_NAME: str = os.getenv("APP_NAME", "ReconAI")
        APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
        DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
        DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./reconai.db")
        OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
        OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        EMBEDDING_DIMENSIONS: int = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
        PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
        PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "reconai-transactions")
        PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
        EXACT_MATCH_THRESHOLD: float = float(os.getenv("EXACT_MATCH_THRESHOLD", "1.0"))
        FUZZY_MATCH_THRESHOLD: float = float(os.getenv("FUZZY_MATCH_THRESHOLD", "0.85"))
        LEVENSHTEIN_THRESHOLD: float = float(os.getenv("LEVENSHTEIN_THRESHOLD", "0.80"))
        AMOUNT_TOLERANCE_PERCENT: float = float(os.getenv("AMOUNT_TOLERANCE_PERCENT", "0.5"))
        AMOUNT_TOLERANCE_ABSOLUTE: float = float(os.getenv("AMOUNT_TOLERANCE_ABSOLUTE", "100.0"))
        AUTO_RESOLVE_MAX_AMOUNT: float = float(os.getenv("AUTO_RESOLVE_MAX_AMOUNT", "10000.0"))
        MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "10000"))
        REQUIRE_HUMAN_APPROVAL_ABOVE: float = float(os.getenv("REQUIRE_HUMAN_APPROVAL_ABOVE", "10000.0"))
        HOST: str = os.getenv("HOST", "0.0.0.0")
        PORT: int = int(os.getenv("PORT", "5000"))
        CORS_ORIGINS: list = ["*"]


settings = Settings()
