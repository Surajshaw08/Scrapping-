from typing import List
from fastapi import APIRouter, Query
from app.scraper.ncd import scrape_ncd
from app.schemas.ncd import NCD, ScrapeBatchRequest, ScrapeBatchItem

router = APIRouter(prefix="/ncd", tags=["NCD"])


@router.get("/scrape", response_model=NCD)
def scrape_ncd_api(
    url: str = Query(..., description="Chittorgarh NCD URL")
):
    """Scrape a single NCD page by URL."""
    return scrape_ncd(url)


@router.post("/scrape/batch", response_model=List[ScrapeBatchItem])
def scrape_ncd_batch(body: ScrapeBatchRequest):
    """
    Scrape multiple NCD pages. Accepts an array of Chittorgarh NCD URLs
    and returns one result per URL (in order). Each item has `url`, `data` (NCD when ok),
    and `error` (message when scrape failed).
    """
    results: List[ScrapeBatchItem] = []
    for u in body.urls:
        try:
            raw = scrape_ncd(u)
            results.append(ScrapeBatchItem(url=u, data=NCD.model_validate(raw), error=None))
        except Exception as e:
            results.append(ScrapeBatchItem(url=u, data=None, error=str(e)))
    return results
