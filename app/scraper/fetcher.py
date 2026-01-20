import requests
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.google.com/",
}

# Temporary directory for saving fetched HTML (gitignored)
HTML_TEMP_DIR = Path("html_temp")
HTML_TEMP_DIR.mkdir(exist_ok=True)


def get_html_file_path(url: str) -> Path:
    """Get the file path for a given URL (in html_temp)."""
    external_id = url.rstrip("/").split("/")[-1]
    return HTML_TEMP_DIR / f"{external_id}.html"


def get_metadata_file_path(url: str) -> Path:
    """Get the metadata file path for a given URL (in html_temp)."""
    external_id = url.rstrip("/").split("/")[-1]
    return HTML_TEMP_DIR / f"{external_id}.json"


def save_html(url: str, html: str, metadata: Optional[dict] = None) -> Path:
    """Save HTML content to file with optional metadata"""
    file_path = get_html_file_path(url)
    file_path.write_text(html, encoding="utf-8")
    
    if metadata:
        metadata_path = get_metadata_file_path(url)
        metadata["saved_at"] = datetime.now().isoformat()
        metadata["url"] = url
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    
    return file_path


def load_html(url: str) -> Optional[str]:
    """Load HTML from saved file if it exists"""
    file_path = get_html_file_path(url)
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return None


def load_metadata(url: str) -> Optional[dict]:
    """Load metadata from saved file if it exists"""
    metadata_path = get_metadata_file_path(url)
    if metadata_path.exists():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    return None


def download_html(url: str, use_cache: bool = True, save_metadata: bool = True) -> str:
    """
    Download HTML from URL and save locally.
    
    Args:
        url: URL to download
        use_cache: If True, use cached HTML if available
        save_metadata: If True, save metadata about the download
    
    Returns:
        HTML content as string
    """
    # Use cached HTML if available and use_cache is True
    if use_cache:
        cached_html = load_html(url)
        if cached_html:
            return cached_html

    # Download fresh HTML
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    html = response.text

    # Save HTML and metadata
    metadata = {
        "content_length": len(html),
        "status_code": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
    } if save_metadata else None
    
    save_html(url, html, metadata)
    return html


def parse_from_saved_html(url: str) -> Optional[str]:
    """
    Parse HTML from a saved file.
    Useful when you want to parse HTML that was previously saved.
    
    Args:
        url: Original URL (used to find the saved HTML file)
    
    Returns:
        HTML content if file exists, None otherwise
    """
    return load_html(url)
