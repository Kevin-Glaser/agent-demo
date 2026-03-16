from fastapi import APIRouter
from .chat import router as chat_router
from .skills import router as skills_router
from .tools import router as tools_router

api_router = APIRouter()
api_router.include_router(chat_router, prefix="/api", tags=["chat"])
api_router.include_router(skills_router, prefix="/api", tags=["skills"])
api_router.include_router(tools_router, prefix="/api", tags=["tools"])
