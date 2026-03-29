import os
from pydantic_settings import BaseSettings
from typing import List


class ModelLimits:
    DEEPSEEK_CHAT = {"context": 128000, "input": 128000, "output": 4096}
    DEEPSEEK_CODER = {"context": 128000, "input": 128000, "output": 4096}
    GPT_4O = {"context": 128000, "input": 128000, "output": 4096}
    GPT_4O_MINI = {"context": 128000, "input": 128000, "output": 4096}
    CLAUDE_3_5_SONNET = {"context": 200000, "input": 200000, "output": 4096}
    CLAUDE_3_5_HAIKU = {"context": 200000, "input": 200000, "output": 4096}
    QWEN_MAX = {"context": 128000, "input": 128000, "output": 4096}
    QWEN_CODER = {"context": 128000, "input": 128000, "output": 4096}
    
    @classmethod
    def get(cls, model: str) -> dict:
        model_lower = model.lower()
        for attr_name in dir(cls):
            if attr_name.startswith("_") or attr_name == "get":
                continue
            attr_value = getattr(cls, attr_name)
            if isinstance(attr_value, dict) and attr_name.lower().replace("_", "-") in model_lower:
                return attr_value
        return {"context": 128000, "input": 128000, "output": 4096}
    
    @classmethod
    def max_output_tokens(cls, model: str) -> int:
        return cls.get(model).get("output", 4096)
    
    @classmethod
    def context_limit(cls, model: str) -> int:
        return cls.get(model).get("context", 128000)
    
    @classmethod
    def input_limit(cls, model: str) -> int:
        return cls.get(model).get("input", 128000)


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
    
    CONVERSATION_MAX_TOKENS: int = 128000
    CONVERSATION_RESERVED_TOKENS: int = 20000
    CONVERSATION_PRUNE_PROTECT: int = 40000
    CONVERSATION_AUTO_COMPACT: bool = True
    
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