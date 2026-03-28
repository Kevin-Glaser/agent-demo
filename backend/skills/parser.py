import os
import yaml
from typing import Optional
from models.skill import SkillInfo, SkillMetadata
from core.exceptions import SkillLoadError


class SkillParser:
    @staticmethod
    def parse_skill_md(skill_md_path: str) -> Optional[SkillInfo]:
        try:
            with open(skill_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.startswith('---'):
                return None
            
            parts = content.split('---', 2)
            if len(parts) < 3:
                return None
            
            frontmatter_str = parts[1].strip()
            skill_content = parts[2].strip()
            
            frontmatter = yaml.safe_load(frontmatter_str)
            
            if not frontmatter or 'name' not in frontmatter or 'description' not in frontmatter:
                return None
            
            metadata = SkillMetadata(
                name=frontmatter.get('name', ''),
                description=frontmatter.get('description', ''),
                license=frontmatter.get('license'),
                compatibility=frontmatter.get('compatibility'),
                metadata=frontmatter.get('metadata')
            )
            
            skill_info = SkillInfo(
                name=metadata.name,
                description=metadata.description,
                skill_md_content=content,
                metadata=metadata,
                file_path=skill_md_path
            )
            
            return skill_info
        
        except Exception as e:
            print(f"Error parsing SKILL.md at {skill_md_path}: {e}")
            return None
