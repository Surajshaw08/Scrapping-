from playwright.sync_api import sync_playwright
from app.utils.helpers import human_delay

def get_html(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # DO NOT change
            args=["--disable-blink-features=AutomationControlled"]
        )

        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata"
        )

        page = context.new_page()
        page.goto(url, timeout=60000)
        human_delay()

        html = page.content()

        browser.close()
        return html
