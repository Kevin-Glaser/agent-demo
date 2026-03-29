import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = ""
    LLM_MODEL: str = "deepseek-chat"
    TEMPERATURE: float = 0.7
    MAX_RETRIES: int = 3
    
    MCP_CONFIG_PATH: str = "mcp.json"
    
    SKILLS_DIRECTORY: str = "storage/skills"
    
    SKILLS_EXTRA_DIRS: str = ""
    
    SKILLS_MAX_IN_PROMPT: int = 50
    SKILLS_MAX_PROMPT_CHARS: int = 8000
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    def get_skills_directories(self) -> List[str]:
        dirs = [self.SKILLS_DIRECTORY]
        if self.SKILLS_EXTRA_DIRS:
            extra = [d.strip() for d in self.SKILLS_EXTRA_DIRS.split(",") if d.strip()]
            dirs.extend(extra)
        return dirs


settings = Settings()
