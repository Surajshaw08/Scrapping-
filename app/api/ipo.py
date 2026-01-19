from fastapi import APIRouter, Query
from app.scraper.chittorgarh import scrape_ipo
from app.schemas.ipo import IPO

router = APIRouter(prefix="/ipo", tags=["IPO"])

@router.get("/scrape", response_model=IPO)
def scrape_ipo_api(
    url: str = Query(..., description="Chittorgarh IPO URL")
):
    return scrape_ipo(url)
