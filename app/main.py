from fastapi import FastAPI
from app.api.ipo import router as ipo_router
from app.api.ncd import router as ncd_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

app.include_router(ipo_router)
app.include_router(ncd_router)