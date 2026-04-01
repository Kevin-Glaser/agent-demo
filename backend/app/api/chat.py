from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models.chat import ChatRequest
from llm.openai_service import llm_service
from skills.manager import skill_manager

router = APIRouter()


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    try:
        use_compact = skill_manager.should_use_compact_format()
        skills_message = skill_manager.build_skills_system_message(compact=use_compact)
        return StreamingResponse(
            llm_service.chat_stream(req, skills_message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM/对话处理失败: {e}")


@router.post("/chat/loop")
async def chat_loop(req: ChatRequest):
    """
    Chat endpoint using the full loop mechanism

    This implements:
    - Full loop control (while + step tracking)
    - AbortController support
    - filter_compacted for message filtering
    - lastUser/lastAssistant/lastFinished tracking
    - Exit condition checking
    - Task processing (subtask/compaction)
    - SessionProcessor for stream handling
    - insertReminders for multi-turn
    - Structured output support
    - maxSteps limitation
    """
    try:
        use_compact = skill_manager.should_use_compact_format()
        skills_message = skill_manager.build_skills_system_message(compact=use_compact)
        max_steps = getattr(req, 'max_steps', 100) if hasattr(req, 'max_steps') else 100
        return StreamingResponse(
            llm_service.run_loop_chat(req, skills_message, max_steps=max_steps),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM/对话处理失败: {e}")


@router.post("/chat")
async def chat(req: ChatRequest):
    try:
        use_compact = skill_manager.should_use_compact_format()
        skills_message = skill_manager.build_skills_system_message(compact=use_compact)
        return await llm_service.chat(req, skills_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM/对话处理失败: {e}")