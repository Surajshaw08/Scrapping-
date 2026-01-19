from fastapi import APIRouter, Query
from app.scraper.ncd import scrape_ncd
from app.schemas.ncd import NCD

router = APIRouter(prefix="/ncd", tags=["NCD"])

@router.get("/scrape", response_model=NCD)
def scrape_ncd_api(
    url: str = Query(..., description="Chittorgarh NCD URL")
):
    return scrape_ncd(url)
