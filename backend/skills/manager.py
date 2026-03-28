import os
import shutil
from typing import Dict, List, Optional

from models.skill import SkillInfo
from skills.loader import SkillLoader
from core.config import settings


class SkillManager:
    def __init__(self, skills_directory: str = None):
        self.skills: Dict[str, SkillInfo] = {}
        self.skills_directory = skills_directory or settings.SKILLS_DIRECTORY
        self.loader = SkillLoader(self.skills_directory)
    
    def set_skills_directory(self, directory: str):
        self.skills_directory = directory
        self.loader.skills_directory = directory
        os.makedirs(directory, exist_ok=True)
    
    def load_skill_from_zip(self, zip_path: str) -> Optional[SkillInfo]:
        skill_info = self.loader.load_from_zip(zip_path)
        if skill_info:
            self.skills[skill_info.name] = skill_info
        return skill_info
    
    def load_all_skills(self):
        skills = self.loader.load_all_from_directory(self.skills_directory)
        for skill in skills:
            self.skills[skill.name] = skill
    
    def get_skill(self, skill_name: str) -> Optional[SkillInfo]:
        return self.skills.get(skill_name)
    
    def get_all_skills(self) -> List[SkillInfo]:
        return list(self.skills.values())
    
    def get_skills_metadata(self) -> List[Dict]:
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "license": skill.metadata.license if skill.metadata else None,
                "compatibility": skill.metadata.compatibility if skill.metadata else None,
                "metadata": skill.metadata.metadata if skill.metadata else None
            }
            for skill in self.skills.values()
        ]
    
    def remove_skill(self, skill_name: str) -> bool:
        if skill_name not in self.skills:
            return False
        
        skill_info = self.skills[skill_name]
        
        if skill_info.file_path and os.path.exists(skill_info.file_path):
            skill_dir = os.path.dirname(skill_info.file_path)
            if os.path.exists(skill_dir):
                shutil.rmtree(skill_dir)
        
        del self.skills[skill_name]
        return True
    
    def build_skills_system_message(self) -> str:
        if not self.skills:
            return ""
        
        skills_intro = "你拥有以下技能(Skills),可以根据需要自动调用:\n\n"
        
        for skill in self.skills.values():
            skills_intro += f"**技能名称**: {skill.name}\n"
            skills_intro += f"**描述**: {skill.description}\n\n"
        
        skills_intro += "当用户的请求与某个技能相关时,你应该主动使用该技能来完成任务。\n"
        
        return skills_intro


skill_manager = SkillManager()
