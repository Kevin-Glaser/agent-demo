from fastapi import APIRouter, HTTPException
from models.chat import ChatRequest
from llm.openai_service import llm_service
from skills.manager import skill_manager

router = APIRouter()


@router.post("/chat")
async def chat(req: ChatRequest):
    try:
        skills_message = skill_manager.build_skills_system_message()
        return await llm_service.chat(req, skills_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM/对话处理失败: {e}")