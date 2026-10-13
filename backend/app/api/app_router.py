from fastapi import APIRouter

from app.api.routers.avatar import router as avatar_router
from app.api.routers.config import router as config_router
from app.api.routers.delivery import router as delivery_router
from app.api.routers.dashboard import router as dashboard_router
from app.api.routers.evaluate import router as evaluate_router
from app.api.routers.exercise import router as exercise_router
from app.api.routers.export import router as export_router
from app.api.routers.integration import router as integration_router
from app.api.routers.knowledge import router as knowledge_router
from app.api.routers.mindmap import router as mindmap_router
from app.api.routers.multimodal import router as multimodal_router
from app.api.routers.path import router as path_router
from app.api.routers.ppt import router as ppt_router
from app.api.routers.profile import router as profile_router
from app.api.routers.push import router as push_router
from app.api.routers.resources import router as resources_router
from app.api.routers.tutor import router as tutor_router
from app.api.routers.voice import router as voice_router
from app.api.routers.workshop import router as workshop_router
from app.evolution import router as evolution_router


api_router = APIRouter()
api_router.include_router(avatar_router)
api_router.include_router(config_router)
api_router.include_router(dashboard_router)
api_router.include_router(delivery_router)
api_router.include_router(profile_router)
api_router.include_router(workshop_router)
api_router.include_router(ppt_router)
api_router.include_router(resources_router)
api_router.include_router(knowledge_router)
api_router.include_router(mindmap_router)
api_router.include_router(multimodal_router)
api_router.include_router(path_router)
api_router.include_router(push_router)
api_router.include_router(tutor_router)
api_router.include_router(voice_router)
api_router.include_router(evaluate_router)
api_router.include_router(exercise_router)
api_router.include_router(evolution_router)
api_router.include_router(export_router)
api_router.include_router(integration_router)

