from backend.models.skill import SkillInfo
import os
import re
import glob
import zipfile
import tempfile
import shutil
from typing import Optional, List, Tuple
from pathlib import Path

from models.skill import SkillInfo
from skills.parser import SkillParser
from core.config import settings
from core.exceptions import SkillLoadError


def sanitize_filename(name: str) -> str:
    return re.sub(r'[<>:"|?*]', '_', name)


class SkillLoader:
    def __init__(self, skills_directories: str | List[str] = None):
        if isinstance(skills_directories, str):
            self.skills_directories = [skills_directories]
        elif skills_directories:
            self.skills_directories = skills_directories
        else:
            self.skills_directories = settings.get_skills_directories()
        self.parser = SkillParser()
    
    def set_directories(self, directories: List[str]):
        self.skills_directories = directories
    
    def load_from_directory(self, skill_dir: str) -> Optional[SkillInfo]:
        skill_md_path = os.path.join(skill_dir, 'SKILL.md')
        
        if not os.path.exists(skill_md_path):
            print(f"SKILL.md not found in {skill_dir}")
            return None
        
        return self.parser.parse_skill_md(skill_md_path)
    
    def load_from_zip(self, zip_path: str, dest_directory: str = None) -> Optional[SkillInfo]:
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                for root, dirs, files in os.walk(temp_dir):
                    if 'SKILL.md' in files:
                        skill_dir = root
                        skill_info = self.load_from_directory(skill_dir)
                        
                        if skill_info and dest_directory:
                            skill_name = skill_info.name
                            safe_skill_name = sanitize_filename(skill_name)
                            dest_dir = os.path.join(dest_directory, safe_skill_name)
                            
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
    
    def scan_for_skills(self, base_dir: str) -> List[Tuple[str, str]]:
        skill_md_files = []
        pattern = os.path.join(base_dir, "**", "SKILL.md")
        for path in glob.glob(pattern, recursive=True):
            rel_dir = os.path.dirname(path)
            skill_name = os.path.basename(rel_dir)
            skill_md_files.append((skill_name, rel_dir))
        return skill_md_files
    
    def load_all_from_directories(self) -> List[SkillInfo]:
        loaded_skills = {}
        seen_names = set()
        
        for base_dir in self.skills_directories:
            if not os.path.exists(base_dir):
                continue
            
            for skill_name, skill_dir in self.scan_for_skills(base_dir):
                if skill_name in seen_names:
                    continue
                
                skill_info = self.load_from_directory(skill_dir)
                if skill_info:
                    loaded_skills[skill_info.name] = skill_info
                    seen_names.add(skill_name)
                    print(f"Loaded skill: {skill_info.name} from {skill_dir}")
            
            for item in os.listdir(base_dir):
                item_path = os.path.join(base_dir, item)
                if item.endswith('.zip') and os.path.isfile(item_path):
                    skill_info = self.load_from_zip(item_path, base_dir)
                    if skill_info and skill_info.name not in seen_names:
                        loaded_skills[skill_info.name] = skill_info
                        seen_names.add(skill_info.name)
                        print(f"Loaded skill from zip: {skill_info.name}")
        
        return list[SkillInfo](loaded_skills.values())
    
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