from typing import Any, Dict, Optional
from pydantic import BaseModel


class SkillMetadata(BaseModel):
    name: str
    description: str
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SkillInfo(BaseModel):
    name: str
    description: str
    skill_md_content: str
    metadata: Optional[SkillMetadata] = None
    file_path: Optional[str] = None
