from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from mcp_client.client import mcp_client
from skills.manager import skill_manager
from app.api import api_router
from core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_client.load_config()
    await mcp_client.load_all_tools()
    
    skill_manager.set_skills_directory(settings.SKILLS_DIRECTORY)
    skill_manager.load_all_skills()
    
    yield


app = FastAPI(
    title="MCP Agent",
    description="AI Agent with MCP and Skills support",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

app.mount("/static", StaticFiles(directory="public"), name="static")


@app.get("/")
async def index():
    return FileResponse("public/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
