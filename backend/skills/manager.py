import os
import shutil
from typing import Dict, List, Optional

from models.skill import SkillInfo
from skills.loader import SkillLoader
from skills.watcher import SkillWatcher
from core.config import settings


class SkillManager:
    def __init__(self, skills_directories: str | List[str] = None):
        self.skills: Dict[str, SkillInfo] = {}
        self.loader = SkillLoader(skills_directories)
        self.watcher: Optional[SkillWatcher] = None
    
    def set_skills_directories(self, directories: List[str]):
        self.loader.set_directories(directories)
        if self.watcher:
            self.watcher.update_directories(directories)
    
    def load_skill_from_zip(self, zip_path: str) -> Optional[SkillInfo]:
        skill_info = self.loader.load_from_zip(zip_path, self.loader.skills_directories[0] if self.loader.skills_directories else None)
        if skill_info:
            self.skills[skill_info.name] = skill_info
        return skill_info
    
    def load_all_skills(self):
        skills = self.loader.load_all_from_directories()
        self.skills.clear()
        for skill in skills:
            self.skills[skill.name] = skill
    
    def reload_skills(self):
        print("Reloading skills...")
        self.load_all_skills()
    
    def start_watcher(self):
        directories = settings.get_skills_directories()
        existing_dirs = [d for d in directories if os.path.exists(d)]
        if existing_dirs:
            self.watcher = SkillWatcher(
                directories=existing_dirs,
                callback=self.reload_skills,
                debounce_ms=500
            )
            self.watcher.start()
    
    def stop_watcher(self):
        if self.watcher:
            self.watcher.stop()
            self.watcher = None
    
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
    
    def build_skills_system_message(self, compact: bool = False) -> str:
        if not self.skills:
            return "<skill>\n  <name>无可用技能</name>\n  <description>当前没有可用的技能</description>\n</skill>"
        
        if compact:
            return self._build_compact_message()
        else:
            return self._build_verbose_message()
    
    def _build_verbose_message(self) -> str:
        skills_xml = []
        for skill in self.skills.values():
            skills_xml.append(f"  <skill>\n    <name>{skill.name}</name>\n    <description>{skill.description}</description>\n  </skill>")
        return "\n".join(skills_xml)
    
    def _build_compact_message(self) -> str:
        skills_xml = []
        for skill in self.skills.values():
            skills_xml.append(f"  <skill>\n    <name>{skill.name}</name>\n    <location>{skill.file_path or 'unknown'}</location>\n  </skill>")
        return "\n".join(skills_xml)
    
    def should_use_compact_format(self) -> bool:
        verbose_msg = self._build_verbose_message()
        return len(verbose_msg) > settings.SKILLS_MAX_PROMPT_CHARS or len(self.skills) > settings.SKILLS_MAX_IN_PROMPT


skill_manager = SkillManager()