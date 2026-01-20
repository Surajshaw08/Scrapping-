import re
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Optional

from app.scraper.fetcher import download_html, parse_from_saved_html
from app.scraper.parser import (
    get_value_by_label_contains,
    get_value_by_label_in_li,
    get_value_from_cards,
    find_card_by_heading,
    parse_registrar_info_ul,
    extract_list,
    extract_section_by_heading,
    extract_link_by_text,
    extract_faqs,
    extract_text_by_selector,
    extract_all_text_by_selector,
    extract_table_data,
)
from app.utils.normalizers import parse_float, parse_int, parse_date
from app.utils.helpers import clean_text


def scrape_ipo_from_file(file_path: str) -> dict:
    """
    Scrape IPO data directly from a saved HTML file.
    
    Args:
        file_path: Path to the HTML file
    
    Returns:
        Dictionary containing all scraped IPO data
    
    Example:
        data = scrape_ipo_from_file("html_temp/12345.html")
    """
    html_path = Path(file_path)
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {file_path}")
    
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    
    # Try to extract URL from metadata or HTML
    url = None
    metadata_path = html_path.parent / f"{html_path.stem}.json"
    if metadata_path.exists():
        import json
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        url = metadata.get("url")
    
    # If no URL in metadata, try to find it in HTML
    if not url:
        url_elem = soup.find("meta", property="og:url") or soup.find("link", rel="canonical")
        if url_elem:
            url = url_elem.get("content") or url_elem.get("href")
    
    if not url:
        # Generate a dummy URL for processing
        external_id = html_path.stem
        url = f"https://www.chittorgarh.com/ipo/{external_id}/"
    
    # Use the main scraping function with the HTML we already have
    return _scrape_ipo_from_soup(soup, url)


def scrape_ipo(url: str, use_saved_html: bool = False) -> dict:
    """
    Scrape IPO data from Chittorgarh website.
    
    Args:
        url: URL of the IPO page
        use_saved_html: If True, use previously saved HTML instead of downloading
    
    Returns:
        Dictionary containing all scraped IPO data
    
    Example:
        # Download and scrape
        data = scrape_ipo("https://www.chittorgarh.com/ipo/12345/")
        
        # Use saved HTML
        data = scrape_ipo("https://www.chittorgarh.com/ipo/12345/", use_saved_html=True)
    """
    # Get HTML - either from saved file or download fresh
    if use_saved_html:
        html = parse_from_saved_html(url)
        if not html:
            raise FileNotFoundError(f"No saved HTML found for URL: {url}")
    else:
        html = download_html(url)
    
    soup = BeautifulSoup(html, "lxml")
    return _scrape_ipo_from_soup(soup, url)


def _get_ipo_value(soup: BeautifulSoup, label: str, parse_func=None):
    """Try top-ratios (li/span), then td, then cards. Optionally parse (parse_float, parse_int)."""
    raw = (
        get_value_by_label_in_li(soup, label)
        or get_value_by_label_contains(soup, label)
        or get_value_from_cards(soup, label)
    )
    if raw and parse_func:
        return parse_func(raw)
    return raw


def _parse_issue_size_crore(s: str):
    """From '46,57,00,000 shares (agg. up to ₹1,069 Cr)' prefer the ₹X Cr part."""
    if not s:
        return None
    m = re.search(r"[\u20b9₹]?\s*([\d,]+)\s*[Cc]r", s)
    if m:
        return parse_float(m.group(1).replace(",", ""))
    return parse_float(s)


def _parse_price_band(s: str):
    """From '₹21 to ₹23' return (low, high). From '₹23 per share' return (23, 23)."""
    if not s:
        return None, None
    nums = re.findall(r"[\u20b9₹]?\s*(\d+(?:\.\d+)?)", s)
    if not nums:
        return None, None
    f = [float(x) for x in nums]
    return (min(f), max(f))


def _parse_bse_nse(s: str):
    """From '544678 / BHARATCOAL' return (bse_code, nse_code)."""
    if not s:
        return None, None
    parts = [p.strip() for p in re.split(r"\s*/\s*", s)]
    bse = parts[0] if len(parts) > 0 and parts[0].isdigit() else None
    nse = parts[1] if len(parts) > 1 else None
    return (bse, nse)


def _extract_lot_size_table(soup: BeautifulSoup) -> dict:
    """From IPO Lot Size table: single_lot_price (Retail Min Amount), small_hni_lot (S-HNI Min Lots), big_hni_lot (B-HNI Min Lots)."""
    out = {}
    table = soup.find("div", id="lotSizeTable")
    if not table:
        table = find_card_by_heading(soup, "IPO Lot Size")
    if not table:
        return out
    tbl = table.find("table")
    if not tbl:
        return out
    rows = tbl.find_all("tr")
    headers = [clean_text(th.get_text()).lower() for th in rows[0].find_all("th")] if rows else []
    app_idx = next((i for i, h in enumerate(headers) if "application" in h or "app" in h), 0)
    lots_idx = next((i for i, h in enumerate(headers) if "lot" in h), 1)
    amt_idx = next((i for i, h in enumerate(headers) if "amount" in h or "amt" in h), 3)
    for tr in rows[1:]:
        cells = tr.find_all("td")
        if len(cells) <= max(app_idx, lots_idx, amt_idx):
            continue
        app = clean_text(cells[app_idx].get_text()).lower()
        if "retail" in app and "min" in app:
            out["single_lot_price"] = parse_float(clean_text(cells[amt_idx].get_text()))
        elif "s-hni" in app and "min" in app:
            out["small_hni_lot"] = parse_int(clean_text(cells[lots_idx].get_text()))
        elif "b-hni" in app and "min" in app:
            out["big_hni_lot"] = parse_int(clean_text(cells[lots_idx].get_text()))
    return out


def _extract_doc_urls(soup: BeautifulSoup) -> dict:
    """From Docs dropdown and links: DRHP, RHP, Final Prospectus, Anchor. Prefer sebi.gov.in and chittorgarh PDFs."""
    out = {}
    for a in soup.find_all("a", href=True):
        h = a.get("href", "")
        t = clean_text(a.get_text()).lower()
        if not ("sebi.gov.in" in h or "chittorgarh.net" in h or h.endswith(".pdf")):
            continue
        full = h if h.startswith("http") else "https://www.chittorgarh.com" + h
        if "drhp" in t:
            out["drhp"] = full
        elif "final" in t or "prospectus" in t:
            out["final_prospectus"] = full
        elif "rhp" in t:
            out["rhp"] = full
        elif "anchor" in t:
            out["anchor"] = full
    return out


def _scrape_ipo_from_soup(soup: BeautifulSoup, url: str) -> dict:
    """Internal function to scrape from BeautifulSoup object"""
    name_elem = soup.find("h1")
    name = name_elem.get_text(strip=True) if name_elem else ""
    external_id = int(url.rstrip("/").split("/")[-1])
    slug = url.split("/ipo/")[1].split("/")[0] if "/ipo/" in url else ""
    status = _get_ipo_value(soup, "Status") or ""

    # Issue size: prefer Total Issue Size and parse ₹X Cr
    issue_size_crore = _parse_issue_size_crore(
        _get_ipo_value(soup, "Total Issue Size") or _get_ipo_value(soup, "Issue Size")
    )

    # Fresh / OFS: from table labels, or infer from Sale Type + issue_size, or from summary "offer for sale ... ₹X crore"
    fresh_issue_crore = parse_float(_get_ipo_value(soup, "Fresh Issue") or _get_ipo_value(soup, "Fresh Issue (Rs Cr)"))
    ofs_issue_crore = parse_float(_get_ipo_value(soup, "Offer for Sale") or _get_ipo_value(soup, "OFS") or _get_ipo_value(soup, "Offer for Sale (Rs Cr)"))
    sale_type = (_get_ipo_value(soup, "Sale Type") or "").lower()
    if (fresh_issue_crore is None and ofs_issue_crore is None) and issue_size_crore:
        if "offer for sale" in sale_type or "ofs" in sale_type:
            ofs_issue_crore = issue_size_crore
            fresh_issue_crore = 0
        elif "fresh" in sale_type and "sale" not in sale_type:
            fresh_issue_crore = issue_size_crore
            ofs_issue_crore = 0
    if ofs_issue_crore is None and issue_size_crore:
        for blk in [soup.find("div", id="ipoSummary"), soup.find("div", class_=lambda c: c and "ipo-dynamic-content" in (c if isinstance(c, str) else " ".join(c or [])))]:
            if blk and "offer for sale" in (blk.get_text() or "").lower():
                m = re.search(r"[\u20b9₹]?\s*([\d,]+(?:\.[\d]+)?)\s*[Cc]rore", blk.get_text())
                if m:
                    ofs_issue_crore = parse_float(m.group(1).replace(",", ""))
                    if fresh_issue_crore is None:
                        fresh_issue_crore = 0
                    break

    # Price band
    pb = _get_ipo_value(soup, "Price Band")
    issue_price_low, issue_price_high = _parse_price_band(pb)
    if issue_price_low is None:
        ip = _get_ipo_value(soup, "Issue Price") or get_value_from_cards(soup, "Issue Price")
        p = parse_float(ip) if ip else None
        issue_price_low = issue_price_high = p

    # BSE / NSE from combined cell (e.g. "544678 / BHARATCOAL")
    bse_nse_raw = (
        _get_ipo_value(soup, "BSE Script Code")
        or _get_ipo_value(soup, "NSE Symbol")
        or _get_ipo_value(soup, "BSE Script")
        or get_value_by_label_contains(soup, "BSE Script")
    )
    bse_code, nse_code = _parse_bse_nse(bse_nse_raw) if bse_nse_raw else (None, None)
    if not bse_code:
        bse_code = _get_ipo_value(soup, "BSE Code")
    if not nse_code:
        nse_code = _get_ipo_value(soup, "NSE Symbol")

    # Lot size table for single_lot_price, small_hni_lot, big_hni_lot
    lot_info = _extract_lot_size_table(soup)

    # Document URLs from Docs dropdown (sebi, RHP, DRHP, Prospectus, Anchor)
    doc_urls = _extract_doc_urls(soup)

    # Logo: .logo-container img, og:image, img[alt*="Logo"]
    logo_url = (
        extract_text_by_selector(soup, ".logo-container img", "src")
        or extract_text_by_selector(soup, "img[alt*='Logo']", "src")
    )
    if not logo_url:
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            logo_url = og["content"]
    if logo_url and logo_url.startswith("/"):
        logo_url = "https://www.chittorgarh.net" + logo_url

    allotment_date = _extract_date(soup, ["Allotment", "Allotment Date"])
    boa_date = _extract_date(soup, ["Basis of Allotment", "BOA", "BoA"]) or allotment_date

    data = {
        "external_id": external_id,
        "slug": slug,
        "name": name,
        "category": "IPO",
        "exchange": _get_ipo_value(soup, "Exchange") or _get_ipo_value(soup, "Listing At") or "BSE & NSE",

        "issue_size_crore": issue_size_crore,
        "fresh_issue_crore": fresh_issue_crore,
        "ofs_issue_crore": ofs_issue_crore,
        "market_maker_reserved_crore": parse_float(_get_ipo_value(soup, "Market Maker") or _get_ipo_value(soup, "Market Maker Reserved")),

        "face_value": parse_float(_get_ipo_value(soup, "Face Value")),
        "issue_type": _get_ipo_value(soup, "Issue Type"),

        "issue_price_low": issue_price_low,
        "issue_price_high": issue_price_high,
        "lot_size": parse_int(_get_ipo_value(soup, "Lot Size")),
        "single_lot_price": lot_info.get("single_lot_price") or parse_float(_get_ipo_value(soup, "Lot Investment")),
        "small_hni_lot": lot_info.get("small_hni_lot"),
        "big_hni_lot": lot_info.get("big_hni_lot"),

        "issue_open_date": _extract_date(soup, ["IPO Open", "Issue Open", "Open Date"]),
        "issue_close_date": _extract_date(soup, ["IPO Close", "Issue Close", "Close Date"]),
        "allotment_date": allotment_date,
        "refund_date": _extract_date(soup, ["Refund", "Refund Date"]),
        "listing_date": _extract_date(soup, ["Listed on", "Listing Date", "Listing"]),
        "boa_date": boa_date,
        "cos_date": _extract_date(soup, ["Credit of Shares", "COS", "Credit Date"]),

        "website": extract_link_by_text(soup, "Website") or _get_ipo_value(soup, "Website"),
        "sector": _extract_sector(soup),
        "bse_code": bse_code,
        "nse_code": nse_code,

        "promoter_holding_pre": parse_float(_get_ipo_value(soup, "Share Holding Pre Issue") or _get_ipo_value(soup, "Promoter Holding")),
        "promoter_holding_post": parse_float(_get_ipo_value(soup, "Share Holding Post Issue") or _get_ipo_value(soup, "Post Issue")),

        "about_company": _extract_about_company(soup),
        "strengths": _extract_strengths(soup),
        "weaknesses": _extract_weaknesses(soup),
        "opportunities": _extract_opportunities(soup),
        "threats": _extract_threats(soup),
        "products": _extract_products(soup),
        "services": _extract_services(soup),
        "promoters": _extract_promoters(soup),
        "lead_managers": _extract_lead_managers(soup),

        "objectives": _extract_objectives(soup),
        "financials": _extract_financials(soup),
        "peers": _extract_peers(soup),
        "company_contacts": _extract_company_contacts(soup),
        "registrar": _extract_registrar(soup),
        "reservations": _extract_reservations(soup),
        "rhp_insights": _extract_rhp_insights(soup),

        "drhp_url": doc_urls.get("drhp") or extract_link_by_text(soup, "DRHP"),
        "rhp_url": doc_urls.get("rhp") or extract_link_by_text(soup, "RHP"),
        "final_prospectus_url": doc_urls.get("final_prospectus") or extract_link_by_text(soup, "Final Prospectus"),
        "anchor_list_url": doc_urls.get("anchor") or extract_link_by_text(soup, "Anchor Investor Link") or extract_link_by_text(soup, "Anchor"),
        "logo_url": logo_url or extract_text_by_selector(soup, "img.logo, .company-logo img", "src"),

        "isTentative": "Tentative" in name or "Tentative" in status,
        "rating": parse_float(_get_ipo_value(soup, "Rating") or _get_ipo_value(soup, "IPO Rating")),
        "listing_price": parse_float(_get_ipo_value(soup, "Listing Price") or _get_ipo_value(soup, "Listing Price (Rs)")),

        "faqs": extract_faqs(soup),
    }

    return data


def _extract_about_company(soup: BeautifulSoup) -> list:
    """Extract about from #ipoSummary, #about-company-section: p and ul li (excl. Competitive Strengths list)."""
    about = []
    exclude = ["IPO Reports", "eBook", "Broker", "Zerodha", "Angel One", "More Brokers", "List of", "Performance", "Read More"]
    section = soup.find("div", id="ipoSummary") or soup.find("div", id="about-company-section")
    if section:
        for p in section.find_all("p"):
            t = clean_text(p.get_text())
            if t and len(t) > 30 and not any(k in t for k in exclude):
                about.append(t)
        # Include list items that are not "Competitive Strengths" sub-heading
        for ul in section.find_all("ul"):
            prev = ul.find_previous(["p", "strong"])
            pt = (prev.get_text() or "").lower() if prev else ""
            if prev and "competitive" in pt and ("strength" in pt or "strenght" in pt):
                continue  # skip strengths, extracted in _extract_strengths
            for li in ul.find_all("li"):
                t = clean_text(li.get_text())
                if t and len(t) > 20 and not any(k in t for k in exclude):
                    about.append(t)
    if not about:
        section = extract_section_by_heading(soup, "About") or extract_section_by_heading(soup, "Company Overview")
        if section:
            for p in section.find_all("p"):
                t = clean_text(p.get_text())
                if t and len(t) > 30:
                    about.append(t)
    return about


def _extract_strengths(soup: BeautifulSoup) -> list:
    """Extract strengths: ul under 'Competitive Strengths' in #ipoSummary, or section by heading."""
    strengths = []
    section = soup.find("div", id="ipoSummary") or soup.find("div", id="about-company-section")
    if section:
        for p in section.find_all("p"):
            t = (p.get_text() or "").lower()
            if "competitive" in t and ("strength" in t or "strenght" in t):
                ul = p.find_next_sibling("ul") or p.find_next("ul")
                if ul:
                    strengths = [clean_text(li.get_text()) for li in ul.find_all("li") if clean_text(li.get_text())]
                    return strengths
    if not strengths:
        section = extract_section_by_heading(soup, "Strengths") or extract_section_by_heading(soup, "Strength")
        if section:
            strengths = extract_list(section) or [clean_text(p.get_text()) for p in section.find_all("p") if clean_text(p.get_text())]
    return strengths


def _extract_weaknesses(soup: BeautifulSoup) -> list:
    """Extract weaknesses: find_card_by_heading, then section by heading or id."""
    section = find_card_by_heading(soup, "Weaknesses", "Weakness") or \
              extract_section_by_heading(soup, "Weaknesses") or \
              extract_section_by_heading(soup, "Weakness") or \
              soup.find("div", id=lambda x: x and "weakness" in (x or "").lower())
    if not section:
        return []
    out = extract_list(section)
    if not out:
        out = [clean_text(p.get_text()) for p in section.find_all("p") if clean_text(p.get_text())]
    return out


def _extract_opportunities(soup: BeautifulSoup) -> list:
    """Extract opportunities: find_card_by_heading, then section by heading or id."""
    section = find_card_by_heading(soup, "Opportunities", "Opportunity") or \
              extract_section_by_heading(soup, "Opportunities") or \
              extract_section_by_heading(soup, "Opportunity") or \
              soup.find("div", id=lambda x: x and "opportunity" in (x or "").lower())
    if not section:
        return []
    out = extract_list(section)
    if not out:
        out = [clean_text(p.get_text()) for p in section.find_all("p") if clean_text(p.get_text())]
    return out


def _extract_threats(soup: BeautifulSoup) -> list:
    """Extract threats: find_card_by_heading, then section by heading or id."""
    section = find_card_by_heading(soup, "Threats", "Threat") or \
              extract_section_by_heading(soup, "Threats") or \
              extract_section_by_heading(soup, "Threat") or \
              soup.find("div", id=lambda x: x and "threat" in (x or "").lower())
    if not section:
        return []
    out = extract_list(section)
    if not out:
        out = [clean_text(p.get_text()) for p in section.find_all("p") if clean_text(p.get_text())]
    return out


def _extract_products(soup: BeautifulSoup) -> list:
    """Extract products: dedicated section, or from #ipoSummary (primary product, production of X,Y,Z, produced X and Y)."""
    products = []
    section = find_card_by_heading(soup, "Products", "Product") or \
              extract_section_by_heading(soup, "Products") or \
              extract_section_by_heading(soup, "Product") or \
              soup.find("div", id=lambda x: x and "product" in (x or "").lower())
    if section:
        products = extract_list(section)
        if not products:
            products = [clean_text(p.get_text()) for p in section.find_all("p") if clean_text(p.get_text())]
    if not products:
        ab = soup.find("div", id="ipoSummary") or soup.find("div", id="about-company-section")
        if ab:
            text = ab.get_text()
            # "production of X, Y, and Z" or "engaged in the production of X, Y and Z"
            m = re.search(r"(?:engaged in the\s+)?production of\s+([^.]+?)(?:\.|$)", text, re.I)
            if m:
                for x in re.split(r",\s*and\s+|\s+and\s+|,", m.group(1)):
                    t = clean_text(x)
                    if t and len(t) > 2:
                        products.append(t)
            # "primary product is X" if production of didn't match
            if not products:
                m = re.search(r"primary\s+product[s]?\s+is\s+([^.]+?)(?:\.|,|$)", text, re.I)
                if m:
                    for x in re.split(r",\s*and\s+|\s+and\s+|,", m.group(1)):
                        t = clean_text(x)
                        if t and len(t) > 2:
                            products.append(t)
    return products


def _extract_services(soup: BeautifulSoup) -> list:
    """Extract services: from #ipoSummary 'operations include' first, then dedicated section (exclude broker/nav)."""
    exclude = ["Broker", "Zerodha", "Angel One", "Kotak", "Motilal", "Upstox", "5Paisa", "More Brokers", "Report", "Review", "Indiabulls", "Full Service", "Full-Service"]
    services = []
    # Prefer #ipoSummary "operations include" / "services include" (main content)
    ab = soup.find("div", id="ipoSummary") or soup.find("div", id="about-company-section")
    if ab:
        text = ab.get_text()
        for pat in [r"operations\s+include\s+([^.]+\.?)", r"services\s+include\s+([^.]+\.?)", r"business\s+includes?\s+([^.]+\.?)"]:
            m = re.search(pat, text, re.I)
            if m:
                block = m.group(1)
                # Split on ", " and " and "; trim leading "and ", trailing comma/period
                for part in re.split(r",\s+|\s+and\s+", block):
                    t = clean_text(part).strip().lstrip("and ").rstrip(".,")
                    if t and 10 < len(t) < 250 and not any(k in t for k in exclude):
                        services.append(t)
                break
    if not services:
        section = find_card_by_heading(soup, "Services", "Service", "Business") or \
                  extract_section_by_heading(soup, "Services") or \
                  extract_section_by_heading(soup, "Service") or \
                  soup.find("div", id=lambda x: x and "service" in (x or "").lower())
        if section:
            # Avoid nav/sidebar: skip if heading looks like "Full Service Brokers" etc.
            h = section.find(["h2", "h3", "h4"]) or (section.find_previous(["h2", "h3", "h4"]) if section else None)
            ht = (h.get_text() or "").lower() if h else ""
            if "broker" not in ht and "full-service" not in ht and "full service" not in ht:
                for li in section.find_all("li"):
                    t = clean_text(li.get_text())
                    if t and not any(k in t for k in exclude):
                        services.append(t)
                if not services:
                    for p in section.find_all("p"):
                        t = clean_text(p.get_text())
                        if t and not any(k in t for k in exclude):
                            services.append(t)
    return services


def _extract_promoters(soup: BeautifulSoup) -> list:
    """Extract promoters: 'X and Y are the company promoters' in KPI/div, or section by heading, or table."""
    promoters = []
    # Method 1: "X and Y are the company promoters" (common in KPI card; use only compact elements)
    skip = {"rs.", "lakh", "mines", "product", "operations", "square kilometre", "tonnes", "ipo ", "apply", "investor"}
    for tag in soup.find_all(["div", "p", "td"]):
        t = clean_text(tag.get_text())
        if "are the company promoter" not in t.lower() or len(t) > 500:
            continue
        m = re.search(r"(.+?)\s+are the company promoters?\.?", t, re.I | re.S)
        if m:
            rest = clean_text(m.group(1))
            if len(rest) > 400:
                continue
            parts = [clean_text(p) for p in re.split(r"\s+and\s+", rest) if clean_text(p)]
            if not parts or any(any(s in (p or "").lower() for s in skip) or len(p or "") > 120 for p in parts):
                continue
            return parts
    # Method 2: find_card_by_heading or section
    section = find_card_by_heading(soup, "Company Promoter", "Promoters", "Promoter") or \
              extract_section_by_heading(soup, "Promoters") or \
              extract_section_by_heading(soup, "Promoter") or \
              soup.find("div", id=lambda x: x and "promoter" in (x or "").lower())
    if section:
        promoters = extract_list(section)
        if not promoters:
            for p in section.find_all("p"):
                t = clean_text(p.get_text())
                if t and "are the company promoter" in t.lower():
                    m = re.search(r"(.+?)\s+are the company promoters?\.?", t, re.I | re.S)
                    if m:
                        for part in re.split(r"\s+and\s+", clean_text(m.group(1))):
                            x = clean_text(part)
                            if x and len(x) > 2:
                                promoters.append(x)
                        return promoters
                elif t and len(t) > 5 and len(t) < 300:
                    promoters.append(t)
        if not promoters:
            for div in section.find_all("div"):
                t = clean_text(div.get_text())
                if t and 10 < len(t) < 200:
                    promoters.append(t)
    # Method 3: table label "Promoters"
    if not promoters:
        pt = get_value_by_label_contains(soup, "Promoter")
        if pt:
            for x in re.split(r"[,;]\s*|\s+and\s+", pt):
                p = clean_text(x)
                if p:
                    promoters.append(p)
    return promoters


def _extract_lead_managers(soup: BeautifulSoup) -> list:
    """Extract lead managers - filters out report links"""
    lead_managers = []
    
    # Filter keywords that indicate report/navigation links
    exclude_keywords = [
        "List of Issues", "No. of Issues", "Performance", "Report",
        "Market Maker", "Registrar", "Broker Report", "IPO Report"
    ]
    
    # Method 1: From ordered list (most reliable)
    lead_manager_section = extract_section_by_heading(soup, "Lead Manager") or \
                          extract_section_by_heading(soup, "IPO Lead Manager")
    
    if lead_manager_section:
        ol = lead_manager_section.find("ol")
        if ol:
            for li in ol.find_all("li"):
                # Extract just the company name (before "A (" or other markers)
                text = clean_text(li.get_text())
                # Filter out report links
                if any(keyword in text for keyword in exclude_keywords):
                    continue
                
                # Extract company name (before parentheses or special markers)
                if "A (" in text:
                    text = text.split("A (")[0].strip()
                elif "(" in text:
                    # Check if it's a company name or report link
                    if "Performance" not in text and "Report" not in text:
                        text = text.split("(")[0].strip()
                
                # Only add if it looks like a company name
                if text and len(text) > 3 and "Ltd" in text or "Limited" in text or "Securities" in text:
                    if text not in lead_managers:
                        lead_managers.append(text)
    
    # Method 2: From links in lead manager section (filter carefully)
    if not lead_managers:
        lead_manager_links = soup.find_all("a", href=lambda x: x and "/ipo-lead-manager-review/" in x)
        for link in lead_manager_links:
            text = clean_text(link.get_text())
            if text and not any(keyword in text for keyword in exclude_keywords):
                if text not in lead_managers:
                    lead_managers.append(text)
    
    # Method 3: From table (last resort)
    if not lead_managers:
        value = get_value_by_label_contains(soup, "Lead Manager")
        if value:
            # Split by comma or newline
            items = [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
            for item in items:
                if not any(keyword in item for keyword in exclude_keywords):
                    if item not in lead_managers:
                        lead_managers.append(item)
    
    return lead_managers


def _extract_objectives(soup: BeautifulSoup) -> list:
    """Extract from table#ObjectiveIssue: #, Issue Objects, Est Amt (₹ Cr.) -> sno, description, amount_crore."""
    out = []
    table = soup.find("table", id=lambda x: x and "objective" in (x or "").lower())
    if not table:
        card = find_card_by_heading(soup, "Objects of the Issue", "Objects")
        if card:
            table = card.find("table")
    if not table:
        return out
    rows = table.find_all("tr")
    if len(rows) < 2:
        return out
    headers = [clean_text(th.get_text()).lower() for th in rows[0].find_all("th")]
    sni = next((i for i, h in enumerate(headers) if h == "#" or "sno" in h), 0)
    desci = next((i for i, h in enumerate(headers) if "object" in h or "desc" in h), 1)
    amti = next((i for i, h in enumerate(headers) if "amt" in h or "amount" in h or "cr" in h), 2)
    for tr in rows[1:]:
        cells = tr.find_all("td")
        if len(cells) <= max(sni, desci, amti):
            continue
        sno = parse_int(clean_text(cells[sni].get_text()))
        desc = clean_text(cells[desci].get_text())
        amt = parse_float(clean_text(cells[amti].get_text())) if amti < len(cells) else None
        if desc:
            out.append({"sno": sno or len(out) + 1, "description": desc, "amount_crore": amt or 0})
    return out


def _extract_financials(soup: BeautifulSoup) -> list:
    """Extract from #financialTable: Period Ended columns, rows Assets, Total Income, PAT, etc."""
    from datetime import datetime
    out = []
    table = soup.find("table", id="financialTable")
    if not table:
        return out
    rows = table.find_all("tr")
    if len(rows) < 2:
        return out
    headers = [clean_text(th.get_text()) for th in rows[0].find_all("th")]
    key_to_row = {"assets": "asset", "total_income": "total income", "pat": "profit after tax",
                  "ebitda": "ebitda", "net_worth": "net worth", "reserves": "reserve", "borrowings": "borrowing"}
    row_vals = {}
    for tr in rows[1:]:
        cells = tr.find_all("td")
        if not cells:
            continue
        label = clean_text(cells[0].get_text()).lower()
        for key, sub in key_to_row.items():
            if sub in label:
                row_vals[key] = [parse_float(clean_text(c.get_text())) for c in cells[1:]]
                break
    n = len(headers) - 1
    for ci in range(n):
        period_label = headers[ci + 1] if ci + 1 < len(headers) else ""
        try:
            dt = datetime.strptime(period_label.strip(), "%d %b %Y")
            period_date = dt.date()
        except Exception:
            period_date = None
        out.append({
            "period_label": period_label,
            "period_end_date": period_date,
            "assets": row_vals.get("assets", [None] * n)[ci] if ci < n else None,
            "total_income": row_vals.get("total_income", [None] * n)[ci] if ci < n else None,
            "pat": row_vals.get("pat", [None] * n)[ci] if ci < n else None,
            "ebitda": row_vals.get("ebitda", [None] * n)[ci] if ci < n else None,
            "net_worth": row_vals.get("net_worth", [None] * n)[ci] if ci < n else None,
            "reserves": row_vals.get("reserves", [None] * n)[ci] if ci < n else None,
            "borrowings": row_vals.get("borrowings", [None] * n)[ci] if ci < n else None,
        })
    return out


def _extract_peers(soup: BeautifulSoup) -> list:
    """Extract from #analysisTable: Company Name, EPS (Basic), EPS (Diluted), NAV, P/E, RONW."""
    out = []
    table = soup.find("table", id="analysisTable")
    if not table:
        return out
    data = extract_table_data(soup, table_id="analysisTable")
    for row in data:
        company = (row.get("Company Name") or row.get("company") or "").strip()
        if not company:
            continue
        out.append({
            "company": company,
            "eps_basic": parse_float(row.get("EPS (Basic)") or row.get("EPS (Basic)")) or 0,
            "eps_diluted": parse_float(row.get("EPS (Diluted)")) or 0,
            "nav": parse_float(row.get("NAV (₹ per share)") or row.get("NAV")) or 0,
            "pe": parse_float(row.get("P/E") or row.get("PE")) or 0,
            "ronw": parse_float(row.get("RoNW") or row.get("RONW") or row.get("RoNW (%)")) or 0,
        })
    return out


def _extract_company_contacts(soup: BeautifulSoup) -> list:
    """Extract company contact from card 'Contact Details': strong, address divs, ul.registrar-info."""
    contacts = []
    card = find_card_by_heading(soup, "Contact Details", "Contact")
    if not card:
        return contacts
    contact_info = {"name": "", "address": "", "phone": "", "email": "", "website": ""}

    strong = card.find("strong")
    if strong:
        contact_info["name"] = clean_text(strong.get_text()).replace(" Address", "").replace("Address", "").strip()

    # Address: divs before ul.registrar-info, excluding strong and ul
    addr_parts = []
    for d in card.find_all("div"):
        if d.find("ul") or d.find("strong"):
            continue
        t = clean_text(d.get_text())
        if t and 2 < len(t) < 150 and "@" not in t and "http" not in t.lower() and t != contact_info["name"]:
            addr_parts.append(t)
    if addr_parts:
        contact_info["address"] = ", ".join(addr_parts)

    ul = card.find("ul", class_=lambda c: c and "registrar-info" in (c if isinstance(c, str) else " ".join(c or [])))
    info = parse_registrar_info_ul(ul)
    contact_info["phone"] = ", ".join(info["phone_numbers"]) if info["phone_numbers"] else ""
    contact_info["email"] = info["email"]
    contact_info["website"] = info["website"]

    if contact_info["name"] or contact_info["address"] or contact_info["email"] or contact_info["phone"]:
        contacts.append(contact_info)
    return contacts


def _extract_registrar(soup: BeautifulSoup) -> Optional[dict]:
    """Extract registrar from card 'IPO Registrar': a.registrar-name, ul.registrar-info."""
    card = find_card_by_heading(soup, "IPO Registrar", "Registrar")
    if not card:
        return None
    registrar = {"name": "", "phone_numbers": [], "email": "", "website": ""}
    a = card.find("a", class_=lambda c: c and "registrar-name" in (c if isinstance(c, str) else " ".join(c or [])))
    if a:
        t = clean_text(a.get_text())
        if t and "Visit" not in t and len(t) > 3:
            registrar["name"] = t
    if not registrar["name"]:
        strong = card.find("strong")
        if strong:
            t = clean_text(strong.get_text())
            if t and "Visit" not in t and len(t) > 3:
                registrar["name"] = t
    ul = card.find("ul", class_=lambda c: c and "registrar-info" in (c if isinstance(c, str) else " ".join(c or [])))
    info = parse_registrar_info_ul(ul)
    registrar["phone_numbers"] = info["phone_numbers"]
    registrar["email"] = info["email"]
    registrar["website"] = info["website"]
    return registrar if registrar["name"] else None


def _extract_reservations(soup: BeautifulSoup) -> list:
    """Extract from IPO Reservation table: parse (X.XX%) from Shares Offered and map to qib, anchor, ex_anchor, nii, bnii, snii, retail, employee, shareholder, total."""
    r = {k: None for k in ["qib", "anchor", "ex_anchor", "nii", "bnii", "snii", "retail", "employee", "shareholder", "other", "total"]}
    card = find_card_by_heading(soup, "IPO Reservation", "Reservation")
    if not card:
        return []
    tbl = card.find("table")
    if not tbl:
        return []
    for tr in tbl.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        label = clean_text(cells[0].get_text()).lower()
        val = clean_text(cells[1].get_text())
        pct = re.search(r"(\d+\.?\d*)\s*%", val)
        p = float(pct.group(1)) if pct else None
        if "qib" in label and "anchor" not in label and "ex" not in label:
            r["qib"] = p
        elif "anchor" in label and "ex" not in label:
            r["anchor"] = p
        elif "ex" in label and "anchor" in label:
            r["ex_anchor"] = p
        elif "bnii" in label or "b-nii" in label:
            r["bnii"] = p
        elif "snii" in label or "s-nii" in label:
            r["snii"] = p
        elif "nii" in label or "hni" in label:
            r["nii"] = p
        elif "retail" in label:
            r["retail"] = p
        elif "employee" in label:
            r["employee"] = p
        elif "shareholder" in label:
            r["shareholder"] = p
        elif "total" in label:
            r["total"] = p
    return [{k: (v or 0) for k, v in r.items()}]


def _extract_date(soup: BeautifulSoup, labels: list):
    """Extract date: cards (IPO Open/Close), top-ratios (Allotment, Refund, Listing, etc.), then td. For BoA, also FAQ 'will be done on'."""
    from app.utils.normalizers import parse_date
    from datetime import datetime
    import re

    def _parse(v):
        if not v:
            return None
        for d in re.findall(r"([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4})", v):
            p = parse_date(d)
            if p:
                return p
        p = parse_date(v)
        if p:
            return p
        try:
            return datetime.strptime(v.strip(), "%A, %B %d, %Y").date()
        except ValueError:
            pass
        return None

    for label in labels:
        v = get_value_from_cards(soup, label) or get_value_by_label_in_li(soup, label) or get_value_by_label_contains(soup, label)
        if v:
            p = _parse(v)
            if p:
                return p

    # BoA: from FAQ/accordion "The finalization of Basis of Allotment ... will be done on Wednesday, January 14, 2026"
    labels_str = str(labels)
    if "Basis of Allotment" in labels_str or "BoA" in labels_str or "BOA" in labels_str:
        for elem in soup.find_all(class_=lambda c: c and "accordion-body" in (c if isinstance(c, str) else " ".join(c or []))):
            txt = elem.get_text() or ""
            if "will be done on" in txt and ("Basis of Allotment" in txt or "allotment" in txt.lower()):
                m = re.search(r"will be done on\s+(?:<!--\s*-->)?\s*([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})", txt)
                if m:
                    p = _parse(m.group(1))
                    if p:
                        return p

    # IPO Date range like "20 to 22 Jan, 2026" or "9 to 13 Jan, 2026"
    if "Open" in labels_str or "Close" in labels_str:
        ipo_date_value = get_value_by_label_contains(soup, "IPO Date")
        if ipo_date_value:
            # Pattern 1: "20 to 22 Jan, 2026"
            range_match = re.search(r'(\d{1,2})\s+to\s+(\d{1,2})\s+([A-Za-z]{3}),\s+(\d{4})', ipo_date_value)
            if range_match:
                day1, day2, month, year = range_match.groups()
                if "Close" in labels_str or "Close Date" in labels_str:
                    date_str = f"{day2} {month} {year}"
                else:
                    date_str = f"{day1} {month} {year}"
                date_val = parse_date(date_str)
                if date_val:
                    return date_val
            
            # Pattern 2: "Jan 20, 2026 to Jan 22, 2026"
            range_match2 = re.search(r'([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})\s+to\s+([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{4})', ipo_date_value)
            if range_match2:
                month1, day1, year1, month2, day2, year2 = range_match2.groups()
                if "Close" in labels_str or "Close Date" in labels_str:
                    date_str = f"{month2} {day2}, {year2}"
                else:
                    date_str = f"{month1} {day1}, {year1}"
                date_val = parse_date(date_str)
                if date_val:
                    return date_val
    
    return None


def _extract_sector(soup: BeautifulSoup) -> Optional[str]:
    """Extract sector: table label Sector/Industry, or keywords in #ipoSummary. Reject plain numbers (e.g. from ratio tables)."""
    for lab in ("Sector", "Industry"):
        v = get_value_by_label_contains(soup, lab)
        if v and any(c.isalpha() for c in (v or "")) and (v.strip().lower() not in ("nse", "bse", "bse, nse")):
            return v
    about_section = soup.find("div", id="ipoSummary") or soup.find("div", id="about-company-section")
    if about_section:
        text = about_section.get_text()
        sectors = ["Coal", "Mining", "Energy", "Technology", "Finance", "Healthcare", "Manufacturing",
                   "Logistics", "Infrastructure", "Real Estate", "Telecom", "FMCG", "Metals"]
        for sec in sectors:
            if sec.lower() in text.lower():
                return sec
    return None


def _extract_rhp_insights(soup: BeautifulSoup) -> list:
    """Extract RHP insights"""
    insights = []
    
    # Look for RHP insights section
    insights_section = extract_section_by_heading(soup, "RHP Insights") or \
                      extract_section_by_heading(soup, "Insights")
    
    if insights_section:
        items = insights_section.find_all(["li", "div", "p"])
        for item in items:
            text = clean_text(item.get_text())
            if text and len(text) > 20:
                insights.append({
                    "tittle": text[:50] + "..." if len(text) > 50 else text,
                    "description": text,
                    "impact": 0  # Default impact
                })
    
    return insights
