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
    extract_table_data,
)
from app.utils.normalizers import parse_float, parse_int, parse_date
from app.utils.helpers import clean_text


def scrape_ncd_from_file(file_path: str) -> dict:
    """
    Scrape NCD data directly from a saved HTML file.
    
    Args:
        file_path: Path to the HTML file
    
    Returns:
        Dictionary containing all scraped NCD data
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
        url = f"https://www.chittorgarh.com/bond/{external_id}/"
    
    return _scrape_ncd_from_soup(soup, url)


def scrape_ncd(url: str, use_saved_html: bool = False) -> dict:
    """
    Scrape NCD data from Chittorgarh website.
    
    Args:
        url: URL of the NCD page
        use_saved_html: If True, use previously saved HTML instead of downloading
    
    Returns:
        Dictionary containing all scraped NCD data
    """
    # Get HTML - either from saved file or download fresh
    if use_saved_html:
        html = parse_from_saved_html(url)
        if not html:
            raise FileNotFoundError(f"No saved HTML found for URL: {url}")
    else:
        html = download_html(url)
    
    soup = BeautifulSoup(html, "lxml")
    return _scrape_ncd_from_soup(soup, url)


def _get_ncd_value(soup: BeautifulSoup, label: str, parse_func=None):
    """Try top-ratios (li/span), then td, then cards. Optionally parse (parse_float, parse_int)."""
    raw = (
        get_value_by_label_in_li(soup, label)
        or get_value_by_label_contains(soup, label)
        or get_value_from_cards(soup, label)
    )
    if raw and parse_func:
        return parse_func(raw)
    return raw


def _scrape_ncd_from_soup(soup: BeautifulSoup, url: str) -> dict:
    """Internal function to scrape NCD from BeautifulSoup object"""
    # Basic information
    name_elem = soup.find("h1")
    issue_name = name_elem.get_text(strip=True) if name_elem else ""

    # Extract slug and issuer from URL or page
    slug = url.split("/bond/")[1].split("/")[0] if "/bond/" in url else ""
    issuer = _extract_issuer(soup, issue_name)

    # Extract description
    description = _extract_description(soup)

    # Extract dates: cards (Open/Close Date) then improved
    open_date = _extract_date_improved(soup, ["Open Date", "Issue Open", "NCD Open", "Open"])
    close_date = _extract_date_improved(soup, ["Close Date", "Issue Close", "NCD Close", "Close"])

    # Issue sizes: top-ratios and cards (Issue Size (Overall))
    issue_size_base = parse_float(_get_ncd_value(soup, "Base Size") or _get_ncd_value(soup, "Issue Size (Base)"))
    issue_size_oversubscription = parse_float(
        _get_ncd_value(soup, "Oversubscription") or _get_ncd_value(soup, "Issue Size (Oversubscription)")
    )
    overall_issue_size = parse_float(
        _get_ncd_value(soup, "Overall Issue Size") or _get_ncd_value(soup, "Issue Size (Overall)")
    )

    # Coupon: from card "Upto 8.9% p.a." and/or from coupon table
    coupon_text = _get_ncd_value(soup, "Coupon Rate") or _get_ncd_value(soup, "Coupon")
    coupon_rate_min = None
    coupon_rate_max = None
    if coupon_text:
        pct = re.findall(r"(\d+\.?\d*)\s*%", coupon_text)
        if pct:
            nums = [float(x) for x in pct]
            coupon_rate_min = min(nums)
            coupon_rate_max = max(nums)
    upto = re.search(r"[Uu]pto\s*(\d+\.?\d*)\s*%", str(_get_ncd_value(soup, "Coupon Rate") or ""))
    if upto:
        coupon_rate_max = max((coupon_rate_max or 0), float(upto.group(1)))

    # NCD details from top-ratios
    face_value_per_ncd = parse_float(
        _get_ncd_value(soup, "Face Value") or _get_ncd_value(soup, "Per NCD")
    )
    issue_price_per_ncd = parse_float(_get_ncd_value(soup, "Issue Price"))
    minimum_lot_size_ncd = parse_float(
        _get_ncd_value(soup, "Minimum Lot") or _get_ncd_value(soup, "Minimum Lot size")
    )
    market_lot_ncd = parse_float(_get_ncd_value(soup, "Market Lot")) or minimum_lot_size_ncd

    # Exchanges and other detail rows
    exchanges = _extract_exchanges(soup)
    security_name = _get_ncd_value(soup, "Security Name")
    security_type = _get_ncd_value(soup, "Security Type")
    basis_of_allotment = _get_ncd_value(soup, "Basis of Allotment")
    debenture_trustee = _get_ncd_value(soup, "Debenture Trustee") or _get_ncd_value(soup, "Debenture Trustee/s")

    # Complex structures
    coupon_series = _extract_coupon_series(soup)
    ratings = _extract_ratings(soup)
    promoters = _extract_promoters(soup)
    objects_of_issue = _extract_objects_of_issue(soup)
    company_contact = _extract_company_contact(soup)
    registrar = _extract_registrar(soup)
    lead_managers = _extract_lead_managers(soup)
    faqs = _extract_faqs(soup)
    documents = _extract_documents(soup)
    company_financials = _extract_company_financials(soup)
    ncd_allocation = _extract_ncd_allocation(soup)

    # Logo: .logo-container img or img[alt*="Logo"]
    logo_url = (
        extract_text_by_selector(soup, ".logo-container img", "src")
        or extract_text_by_selector(soup, "img[alt*='Logo']", "src")
        or extract_text_by_selector(soup, ".broker-image img", "src")
    )
    if logo_url and logo_url.startswith("/"):
        logo_url = "https://www.chittorgarh.net" + logo_url

    # Coupon min/max from series if we have nothing from card/table
    if coupon_series:
        rates = [s.get("coupon_percent_pa") or 0 for s in coupon_series if s.get("coupon_percent_pa")]
        if rates:
            coupon_rate_min = min(rates) if coupon_rate_min is None else min(coupon_rate_min, min(rates))
            coupon_rate_max = max(rates) if coupon_rate_max is None else max(coupon_rate_max, max(rates))

    data = {
        "slug": slug,
        "issuer": issuer,
        "issue_name": issue_name,
        "logo_url": logo_url or None,
        "description": description,
        "open_date": open_date,
        "close_date": close_date,
        "issue_size_overall": overall_issue_size,
        "coupon_rate_min": coupon_rate_min,
        "coupon_rate_max": coupon_rate_max,
        "security_name": security_name,
        "security_type": security_type,
        "issue_size_base": issue_size_base,
        "issue_size_oversubscription": issue_size_oversubscription,
        "overall_issue_size": overall_issue_size,
        "issue_price_per_ncd": issue_price_per_ncd,
        "face_value_per_ncd": face_value_per_ncd,
        "minimum_lot_size_ncd": minimum_lot_size_ncd,
        "market_lot_ncd": market_lot_ncd,
        "exchanges": exchanges,
        "basis_of_allotment": basis_of_allotment,
        "debenture_trustee": debenture_trustee,
        "promoters": promoters,
        "coupon_series": coupon_series,
        "ratings": ratings,
        "company_financials": company_financials,
        "ncd_allocation": ncd_allocation,
        "objects_of_issue": objects_of_issue,
        "company_contact": company_contact,
        "registrar": registrar,
        "lead_managers": lead_managers,
        "documents": documents,
        "faq": faqs,
        "news": [],
    }

    return data


def _extract_issuer(soup: BeautifulSoup, issue_name: str) -> str:
    """Extract issuer name"""
    # Try to extract from issue name (usually format: "Company Name NCD")
    if "NCD" in issue_name:
        issuer = issue_name.split("NCD")[0].strip()
        if issuer:
            return issuer
    
    # Try from page content
    issuer_elem = soup.find("strong", string=lambda x: x and "Ltd" in x) or \
                  soup.find("div", class_=lambda x: x and "issuer" in x.lower())
    if issuer_elem:
        return clean_text(issuer_elem.get_text())
    
    return ""


def _extract_description(soup: BeautifulSoup) -> str:
    """Extract NCD description - from div after .logo-container or similar."""
    # Chittorgarh: div.logo-container followed by div with style font-size and <p>s
    logo_div = soup.select_one(".logo-container")
    if logo_div:
        next_div = logo_div.find_next_sibling("div")
        if next_div:
            pars = next_div.find_all("p")
            if pars:
                parts = [clean_text(p.get_text()) for p in pars if clean_text(p.get_text()) and len(clean_text(p.get_text())) > 40]
                if parts:
                    return clean_text(" ".join(parts[:6]))
    # Fallback: div with style font-size and line-height containing <p>
    for d in soup.find_all("div", style=lambda s: s and "font-size" in (s or "") and "line-height" in (s or "")):
        pars = d.find_all("p")
        if pars:
            parts = [clean_text(p.get_text()) for p in pars if clean_text(p.get_text()) and len(clean_text(p.get_text())) > 40]
            if parts:
                return clean_text(" ".join(parts[:6]))
    return ""


def _extract_date(soup: BeautifulSoup, labels: list):
    """Extract date using multiple label patterns"""
    for label in labels:
        value = get_value_by_label_contains(soup, label)
        if value:
            date = parse_date(value)
            if date:
                return date
    
    return None


def _extract_date_improved(soup: BeautifulSoup, labels: list):
    """Improved date extraction: cards (p.text-muted + p.fs-5), then td, then card divs."""
    import re

    def _parse_date_val(v):
        if not v:
            return None
        dates = re.findall(r"([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4})", v)
        if dates:
            return parse_date(dates[-1] if "Close" in str(labels) else dates[0])
        return parse_date(v)

    for label in labels:
        v = get_value_from_cards(soup, label) or get_value_by_label_in_li(soup, label) or get_value_by_label_contains(soup, label)
        if v:
            d = _parse_date_val(v)
            if d:
                return d

    for label in labels:
        for card in soup.find_all("div", class_=lambda c: c and "card" in (c if isinstance(c, str) else " ".join(c or [])).lower()):
            if label.lower() in (card.get_text() or "").lower():
                p = card.find("p", class_=lambda x: x and "fs-5" in (x if isinstance(x, str) else " ".join(x or [])).lower())
                if p:
                    d = _parse_date_val(clean_text(p.get_text()))
                    if d:
                        return d
    return None


def _extract_exchanges(soup: BeautifulSoup) -> list:
    """Extract exchange names from top-ratios or td (Listing At, Exchange)."""
    import re
    exchange_text = (
        get_value_by_label_in_li(soup, "Listing At")
        or get_value_by_label_in_li(soup, "Exchange")
        or get_value_by_label_contains(soup, "Listing At")
        or get_value_by_label_contains(soup, "Exchange")
    )
    exchanges = []
    if exchange_text:
        for part in re.split(r"[,&]", exchange_text):
            c = clean_text(part)
            if c and "BSE" in c.upper():
                exchanges.append("BSE")
            elif c and "NSE" in c.upper():
                exchanges.append("NSE")
            elif c and c not in exchanges:
                exchanges.append(c)
    seen = set()
    return [x for x in exchanges if not (x in seen or seen.add(x))]


def _extract_coupon_series(soup: BeautifulSoup) -> list:
    """Extract coupon series from table#couponTable: columns Series 1..8, rows Frequency, Nature, Tenor, Coupon, Effective Yield, Amount on Maturity."""
    series = []
    table = soup.find("table", id=lambda x: x and "coupon" in (x or "").lower())
    if not table:
        return series
    thead = table.find("thead")
    tbody = table.find("tbody")
    if not thead or not tbody:
        return series
    headers = [clean_text(th.get_text()) for th in thead.find_all("th")]
    series_cols = [h for i, h in enumerate(headers) if i > 0 and h and ("#" not in h or "Series" in h)]
    if not series_cols:
        series_cols = [f"Series {i+1}" for i in range(max(0, len(headers) - 1))]
    # row_type -> {col_index: value}
    row_map = {}
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        label = clean_text(cells[0].get_text()).lower()
        typ = None
        if "frequency" in label and "interest" in label:
            typ = "freq"
        elif "nature" in label:
            typ = "nature"
        elif "tenor" in label:
            typ = "tenor"
        elif "coupon" in label and "effective" not in label:
            typ = "coupon"
        elif "effective" in label and "yield" in label:
            typ = "eff"
        elif "amount" in label and "maturity" in label:
            typ = "amt"
        if typ:
            row_map[typ] = {i: clean_text(cells[i].get_text()) for i in range(1, len(cells))}
    n = len(series_cols)
    for idx in range(n):
        col = idx + 1  # columns 1..n in table
        freq = (row_map.get("freq") or {}).get(col, "")
        nature = (row_map.get("nature") or {}).get(col, "")
        tenor = (row_map.get("tenor") or {}).get(col, "")
        cou = (row_map.get("coupon") or {}).get(col, "") or "0"
        coup = 0.0 if (cou or "").upper() == "NA" else (parse_float(cou) or 0)
        eff = (row_map.get("eff") or {}).get(col, "") or "0"
        eff_y = 0.0 if (eff or "").upper() == "NA" else (parse_float(eff) or 0)
        amt = (row_map.get("amt") or {}).get(col, "") or "0"
        amt_m = parse_float(amt) or 0
        series.append({
            "series_name": series_cols[idx] if idx < len(series_cols) else f"Series {idx + 1}",
            "frequency_of_interest_payment": freq,
            "nature": nature,
            "tenor": tenor,
            "coupon_percent_pa": coup,
            "effective_yield_percent_pa": eff_y,
            "amount_on_maturity": amt_m,
        })
    return series


def _extract_ratings(soup: BeautifulSoup) -> list:
    """Extract ratings from table#ncd_rating: Rating Agency, NCD Rating, Outlook, Safety Degree, Risk Degree."""
    ratings = []
    table = soup.find("table", id=lambda x: x and "ncd_rating" in (x or "").lower())
    if not table:
        return ratings
    rows = table.find_all("tr")
    if len(rows) < 2:
        return ratings
    headers = [clean_text(th.get_text()) for th in rows[0].find_all("th")]
    for tr in rows[1:]:
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        # Map by header: S.No., Rating Agency, NCD Rating, Outlook, Safety Degree, Risk Degree
        row = {}
        for i, th in enumerate(headers):
            if i < len(cells):
                row[th] = clean_text(cells[i].get_text())
        agency = row.get("Rating Agency", row.get("rating_agency", "")) or (cells[1].get_text() if len(cells) > 1 else "")
        ncd = row.get("NCD Rating", row.get("ncd_rating", "")) or (cells[2].get_text() if len(cells) > 2 else "")
        if agency or ncd:
            ratings.append({
                "rating_agency": clean_text(agency),
                "ncd_rating": clean_text(ncd),
                "outlook": clean_text(row.get("Outlook", row.get("outlook", "")) or (cells[3].get_text() if len(cells) > 3 else "")),
                "safety_degree": clean_text(row.get("Safety Degree", row.get("safety_degree", "")) or (cells[4].get_text() if len(cells) > 4 else "")),
                "risk_degree": clean_text(row.get("Risk Degree", row.get("risk_degree", "")) or (cells[5].get_text() if len(cells) > 5 else "")),
            })
    return ratings


def _extract_promoters(soup: BeautifulSoup) -> list:
    """Extract promoters from 'Company Promoters' section: 'X and Y are the company promoters' or list."""
    promoter_text = (
        get_value_by_label_in_li(soup, "Promoters")
        or get_value_by_label_contains(soup, "Promoters")
    )
    if not promoter_text:
        card = find_card_by_heading(soup, "Company Promoters", "Promoters")
        if card:
            h2 = next((h for h in card.find_all("h2") if "Promoter" in (h.get_text() or "")), None)
            d = h2.find_next_sibling("div") if h2 else None
            if d:
                promoter_text = clean_text(d.get_text())
            else:
                for d in card.find_all("div"):
                    t = d.get_text()
                    if " are the company promoters" in t or (" and " in t and "promoter" in t.lower()):
                        promoter_text = clean_text(t)
                        break
    if promoter_text:
        # "...X and Y are the company promoters." or "X, Y and Z"
        t = re.sub(r"\s+are\s+the\s+company\s+promoters\.?\s*$", "", promoter_text, flags=re.I)
        parts = re.split(r"\s+and\s+|\s*,\s*", t)
        return [clean_text(p) for p in parts if clean_text(p) and len(clean_text(p)) > 2]
    return []


def _extract_objects_of_issue(soup: BeautifulSoup) -> list:
    """Extract objects of issue from section 'Objects of the Issue' (ul with 1–2 sentence items, not key-value rows)."""
    for h in soup.find_all(["h2", "h3"]):
        if "Objects of the Issue" not in (h.get_text() or ""):
            continue
        # Use parent that contains an ul (not top-ratios)
        parent = h.parent
        for _ in range(5):
            if not parent:
                break
            ul = parent.find("ul", class_=lambda c: not c or "top-ratios" not in (c if isinstance(c, str) else " ".join(c or [])))
            if ul and ul.get("class") != ["top-ratios"]:
                items = [clean_text(li.get_text()) for li in ul.find_all("li") if clean_text(li.get_text()) and len(clean_text(li.get_text())) > 15]
                if 1 <= len(items) <= 20:
                    return items
            parent = parent.parent
    return []


def _extract_company_financials(soup: BeautifulSoup) -> Optional[dict]:
    """Extract from table#financialTable: Period Ended, Assets, Total Income, Profit After Tax."""
    table = soup.find("table", id=lambda x: x and "financial" in (x or "").lower())
    if not table:
        return None
    rows = table.find_all("tr")
    if len(rows) < 2:
        return None
    headers = [clean_text(th.get_text()) for th in rows[0].find_all("th")]
    # First col is row type, rest are periods (e.g. 30 Sep 2025, 31 Mar 2025)
    period_cols = [(i, h) for i, h in enumerate(headers) if i > 0 and h and re.search(r"\d{4}", h)]
    row_vals = {}
    for tr in rows[1:]:
        cells = tr.find_all("td")
        if not cells:
            continue
        label = clean_text(cells[0].get_text()).lower()
        if "asset" in label:
            row_vals["assets"] = {i: parse_float(clean_text(cells[i].get_text())) for i, _ in period_cols if i < len(cells)}
        elif "total income" in label:
            row_vals["total_income"] = {i: parse_float(clean_text(cells[i].get_text())) for i, _ in period_cols if i < len(cells)}
        elif "profit after tax" in label or "pat" in label:
            row_vals["profit_after_tax"] = {i: parse_float(clean_text(cells[i].get_text())) for i, _ in period_cols if i < len(cells)}
    periods = []
    for i, period_end in period_cols:
        if i < len(headers):
            periods.append({
                "period_end": period_end,
                "assets": (row_vals.get("assets") or {}).get(i),
                "total_income": (row_vals.get("total_income") or {}).get(i),
                "profit_after_tax": (row_vals.get("profit_after_tax") or {}).get(i),
            })
    if not periods:
        return None
    return {"unit": "Crore", "periods": periods}


def _extract_ncd_allocation(soup: BeautifulSoup) -> Optional[dict]:
    """Extract from NCD Allocation table: Category, Allocated (%)."""
    card = find_card_by_heading(soup, "NCD Allocation")
    if not card:
        return None
    table = card.find("table")
    if not table:
        return None
    rows = table.find_all("tr")
    if len(rows) < 2:
        return None
    headers = [clean_text(th.get_text()) for th in rows[0].find_all("th")]
    cat_idx = next((i for i, h in enumerate(headers) if "categ" in (h or "").lower()), 0)
    pct_idx = next((i for i, h in enumerate(headers) if "allocated" in (h or "").lower() or "%" in (h or "")), 1)
    categories = []
    for tr in rows[1:]:
        cells = tr.find_all("td")
        if len(cells) <= max(cat_idx, pct_idx):
            continue
        cat = clean_text(cells[cat_idx].get_text())
        pct = parse_float(clean_text(cells[pct_idx].get_text()).replace("%", ""))
        if cat and "total" not in cat.lower():
            categories.append({"category": cat, "allocated_percentage": pct or 0, "shares_reserved": 0})
    if not categories:
        return None
    return {"total_shares": 0, "categories": categories}


def _extract_company_contact(soup: BeautifulSoup) -> Optional[dict]:
    """Extract company contact from card with 'Company Contact Information': address + ul.registrar-info."""
    card = find_card_by_heading(soup, "Company Contact Information", "Company Contact")
    if not card:
        return None
    contact = {
        "company_name": "",
        "address_line_1": "",
        "city": "",
        "state": "",
        "pincode": "",
        "phone_numbers": [],
        "email": "",
        "website": "",
    }
    addr = card.find("address")
    if addr:
        strong = addr.find("strong")
        if strong:
            contact["company_name"] = clean_text(strong.get_text())
        p = addr.find("p")
        if p:
            lines = [clean_text(s) for s in p.stripped_strings]
            addr_lines = [x for x in lines if x != contact["company_name"] and len(x) > 2 and "@" not in x and "http" not in x.lower()]
            if addr_lines:
                contact["address_line_1"] = addr_lines[0]
                last = addr_lines[-1]
                pin = re.search(r"\d{6}", last)
                if pin:
                    contact["pincode"] = pin.group()
                    parts = re.split(r",\s*", last)
                    if len(parts) >= 2:
                        contact["city"] = parts[0].strip()
                        contact["state"] = (parts[1] or "").replace(contact["pincode"], "").strip()
    ul = card.find("ul", class_=lambda c: c and "registrar-info" in (c if isinstance(c, str) else " ".join(c or [])))
    info = parse_registrar_info_ul(ul)
    contact["phone_numbers"] = info["phone_numbers"]
    contact["email"] = info["email"] or contact["email"]
    contact["website"] = info["website"] or contact["website"]
    if contact["company_name"] or contact["address_line_1"] or contact["email"] or contact["phone_numbers"]:
        return contact
    return None


def _extract_registrar(soup: BeautifulSoup) -> Optional[dict]:
    """Extract registrar from card 'NCD Registrar': p>a>strong for name, ul.registrar-info for contact."""
    card = find_card_by_heading(soup, "NCD Registrar", "Registrar")
    if not card:
        return None
    registrar = {"name": "", "phone_numbers": [], "email": "", "website": ""}
    strong = card.find("strong")
    if strong:
        t = clean_text(strong.get_text())
        if t and "Visit" not in t and len(t) > 3:
            registrar["name"] = t
    if not registrar["name"]:
        a = card.find("a", href=True)
        if a:
            t = clean_text(a.get_text())
            if t and "Visit" not in t and len(t) > 3:
                registrar["name"] = t
    ul = card.find("ul", class_=lambda c: c and "registrar-info" in (c if isinstance(c, str) else " ".join(c or [])))
    info = parse_registrar_info_ul(ul)
    registrar["phone_numbers"] = info["phone_numbers"]
    registrar["email"] = info["email"]
    registrar["website"] = info["website"]
    return registrar if registrar["name"] else None


def _extract_lead_managers(soup: BeautifulSoup) -> list:
    """Extract lead managers from card 'NCD Lead Manager(s)': ol>li>a."""
    exclude = ["List of Issues", "No. of Issues", "Performance", "Report", "Market Maker", "Registrar", "Broker Report", "IPO Report"]
    card = find_card_by_heading(soup, "NCD Lead Manager", "Lead Manager")
    if not card:
        return []
    ol = card.find("ol")
    if ol:
        out = []
        for li in ol.find_all("li"):
            a = li.find("a", href=True)
            text = clean_text(a.get_text()) if a else clean_text(li.get_text())
            if text and not any(k in text for k in exclude) and len(text) > 3:
                if "(" in text:
                    text = text.split("(")[0].strip()
                if text and text not in out:
                    out.append(text)
        return out
    for a in card.find_all("a", href=lambda h: h and "lead-manager" in h):
        text = clean_text(a.get_text())
        if text and not any(k in text for k in exclude) and len(text) > 3:
            return [text]
    return []


def _extract_faqs(soup: BeautifulSoup) -> list:
    """Extract FAQs"""
    faqs = []
    faq_list = extract_faqs(soup)
    
    for faq in faq_list:
        # extract_faqs returns dict with "answers" key (plural)
        answer = faq.get("answers", "") or faq.get("answer", "")
        faqs.append({
            "question": faq.get("question", ""),
            "answer": answer,
        })
    
    return faqs


def _extract_documents(soup: BeautifulSoup) -> list:
    """Extract document links - filters out navigation links"""
    documents = []
    
    # Filter out navigation/report links
    exclude_keywords = [
        "Upcoming IPOs", "Report List", "Stock Broker", "Stock Market",
        "Other Report", "Mainboard RHP", "SME RHP"
    ]
    
    # Look for document links in specific sections
    doc_section = soup.find("div", class_=lambda x: x and "doc" in x.lower()) or \
                 soup.find("div", id=lambda x: x and "doc" in x.lower())
    
    # Look for document links
    doc_links = soup.find_all("a", href=lambda x: x and any(term in x.lower() for term in ["rhp", "drhp", "prospectus", "document", "sebi.gov.in"]))
    
    for link in doc_links:
        title = clean_text(link.get_text())
        url = link.get("href", "")
        
        # Filter out navigation links
        if any(keyword in title for keyword in exclude_keywords):
            continue
        
        # Only add if it's a real document (SEBI link or has document keywords)
        if title and url:
            if "sebi.gov.in" in url or any(term in url.lower() for term in ["prospectus", "rhp", "drhp"]):
                documents.append({
                    "title": title,
                    "url": url if url.startswith("http") else f"https://www.chittorgarh.com{url}",
                })
    
    return documents
