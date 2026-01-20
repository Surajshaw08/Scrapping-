from typing import List
from fastapi import APIRouter, Query
from app.scraper.chittorgarh import scrape_ipo
from app.schemas.ipo import IPO, ScrapeBatchRequest, ScrapeBatchItem

router = APIRouter(prefix="/ipo", tags=["IPO"])


@router.get("/scrape", response_model=IPO)
def scrape_ipo_api(
    url: str = Query(..., description="Chittorgarh IPO URL")
):
    """Scrape a single IPO page by URL."""
    return scrape_ipo(url)


@router.post("/scrape/batch", response_model=List[ScrapeBatchItem])
def scrape_ipo_batch(body: ScrapeBatchRequest):
    """
    Scrape multiple IPO pages. Accepts an array of Chittorgarh IPO URLs
    and returns one result per URL (in order). Each item has `url`, `data` (IPO when ok),
    and `error` (message when scrape failed).
    """
    results: List[ScrapeBatchItem] = []
    for u in body.urls:
        try:
            raw = scrape_ipo(u)
            results.append(ScrapeBatchItem(url=u, data=IPO.model_validate(raw), error=None))
        except Exception as e:
            results.append(ScrapeBatchItem(url=u, data=None, error=str(e)))
    return results
