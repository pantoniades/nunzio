"""Configuration management for Nunzio."""

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    url: str = Field(
        default="mysql+aiomysql://nunzio:password@odysseus:3306/nunzio_workouts",
        description="SQLAlchemy database URL",
    )
    pool_size: int = Field(default=5, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max overflow connections")
    pool_timeout: int = Field(default=30, description="Pool timeout in seconds")


class LLMConfig(BaseModel):
    """LLM configuration for Ollama."""

    base_url: str = Field(
        default="http://odysseus:11434", description="Ollama base URL"
    )
    model: str = Field(default="llama3.2", description="Default model to use")
    timeout: int = Field(default=60, description="Request timeout in seconds")


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""

    token: str = Field(default="", description="Bot token")
    webhook_url: str | None = Field(default=None, description="Webhook URL (optional)")
    allowed_user_ids: list[int] = Field(
        default_factory=list,
        description="Telegram user IDs allowed to use the bot (empty = no restriction)",
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Log level"
    )
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string",
    )


class Config(BaseSettings):
    """Main application configuration."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Application settings
    debug: bool = Field(default=False, description="Enable debug mode")
    environment: Literal["development", "production"] = Field(
        default="development", description="Application environment"
    )

    class Config:
        env_nested_delimiter = "__"
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global configuration instance
config = Config()
