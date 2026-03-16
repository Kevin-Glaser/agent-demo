import os
import zipfile
import tempfile
import shutil
from typing import Optional
from pathlib import Path

from models.skill import SkillInfo
from skills.parser import SkillParser
from core.config import settings
from core.exceptions import SkillLoadError


class SkillLoader:
    def __init__(self, skills_directory: str = None):
        self.skills_directory = skills_directory or settings.SKILLS_DIRECTORY
        self.parser = SkillParser()
    
    def load_from_directory(self, skill_dir: str) -> Optional[SkillInfo]:
        skill_md_path = os.path.join(skill_dir, 'SKILL.md')
        
        if not os.path.exists(skill_md_path):
            print(f"SKILL.md not found in {skill_dir}")
            return None
        
        return self.parser.parse_skill_md(skill_md_path)
    
    def load_from_zip(self, zip_path: str) -> Optional[SkillInfo]:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                for root, dirs, files in os.walk(temp_dir):
                    if 'SKILL.md' in files:
                        skill_dir = root
                        skill_info = self.load_from_directory(skill_dir)
                        
                        if skill_info and self.skills_directory:
                            skill_name = skill_info.name
                            dest_dir = os.path.join(self.skills_directory, skill_name)
                            
                            if os.path.exists(dest_dir):
                                shutil.rmtree(dest_dir)
                            
                            shutil.copytree(skill_dir, dest_dir)
                            skill_info.file_path = os.path.join(dest_dir, 'SKILL.md')
                            
                            return skill_info
                
                print(f"No SKILL.md found in {zip_path}")
                return None
        
        except Exception as e:
            print(f"Error loading skill from zip {zip_path}: {e}")
            return None
    
    def load_all_from_directory(self, directory: str) -> list[SkillInfo]:
        skills = []
        
        if not os.path.exists(directory):
            print(f"Skills directory not found: {directory}")
            return skills
        
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            
            if os.path.isdir(item_path):
                skill_info = self.load_from_directory(item_path)
                if skill_info:
                    skills.append(skill_info)
                    print(f"Loaded skill: {skill_info.name}")
            
            elif item.endswith('.zip'):
                skill_info = self.load_from_zip(item_path)
                if skill_info:
                    skills.append(skill_info)
                    print(f"Loaded skill from zip: {skill_info.name}")
        
        return skills
