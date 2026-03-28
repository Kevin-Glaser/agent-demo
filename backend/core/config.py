from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""
    LLM_MODEL: str = "deepseek-chat"
    TEMPERATURE: float = 0.7
    MAX_RETRIES: int = 3
    
    MCP_CONFIG_PATH: str = "mcp.json"
    
    SKILLS_DIRECTORY: str = "storage/skills"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
