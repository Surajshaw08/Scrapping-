import random
import time
import re

def human_delay(min_sec=2.5, max_sec=5.5):
    time.sleep(random.uniform(min_sec, max_sec))

def clean_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()

def extract_number(text: str):
    if not text:
        return None
    match = re.search(r"[\d,.]+", text.replace(",", ""))
    return float(match.group()) if match else None
