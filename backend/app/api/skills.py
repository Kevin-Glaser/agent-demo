from fastapi import APIRouter, HTTPException, UploadFile, File
import os
from skills.manager import skill_manager

router = APIRouter()


@router.get("/skills")
async def get_skills():
    return {"skills": skill_manager.get_skills_metadata()}


@router.post("/skills/upload")
async def upload_skill(file: UploadFile = File(...)):
    try:
        if not file.filename.endswith('.zip'):
            raise HTTPException(status_code=400, detail="只支持 .zip 格式的压缩包")
        
        temp_zip_path = f"temp_{file.filename}"
        with open(temp_zip_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        skill_info = skill_manager.load_skill_from_zip(temp_zip_path)
        
        os.remove(temp_zip_path)
        
        if skill_info:
            return {
                "success": True,
                "skill": {
                    "name": skill_info.name,
                    "description": skill_info.description
                }
            }
        else:
            raise HTTPException(status_code=400, detail="无法从压缩包中加载 Skill,请确保包含 SKILL.md 文件")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传 Skill 失败: {str(e)}")


@router.delete("/skills/{skill_name}")
async def delete_skill(skill_name: str):
    success = skill_manager.remove_skill(skill_name)
    if success:
        return {"success": True, "message": f"Skill '{skill_name}' 已删除"}
    else:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' 不存在")
