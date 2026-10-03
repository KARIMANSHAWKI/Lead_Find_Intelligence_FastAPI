from fastapi import APIRouter

from app.api.v1.agent_routes import router as agent_router

router = APIRouter()
router.include_router(agent_router)
