from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Manages application settings loaded from environment variables.
    """
    # --- Security Settings ---
    # Generate a strong secret key using: openssl rand -hex 32
    SECRET_KEY: str = "a_default_secret_key_that_must_be_overridden"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 # 24 hours

    # --- Database Settings ---
    DATABASE_URL: str

    # --- Redis Settings ---
    REDIS_URL: str

    # --- LLM Provider Settings ---
    # API keys for external services
    OPENAI_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    CLAUDE_API_KEY: str | None = None
    TAVILY_API_KEY: str | None = None

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

# Create a single, importable instance of the settings
settings = Settings()
