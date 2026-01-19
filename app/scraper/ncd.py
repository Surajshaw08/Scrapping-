from bs4 import BeautifulSoup
from pathlib import Path
from typing import Optional

from app.scraper.fetcher import download_html, parse_from_saved_html
from app.scraper.parser import (
    get_value_by_label_contains,
    extract_list,
    extract_section_by_heading,
    extract_link_by_text,
    extract_faqs,
    extract_text_by_selector,
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
    
    # Extract dates - improved extraction
    open_date = _extract_date_improved(soup, ["Open Date", "Issue Open", "NCD Open", "Open"])
    close_date = _extract_date_improved(soup, ["Close Date", "Issue Close", "NCD Close", "Close"])
    
    # Extract issue details - improved with multiple patterns
    issue_size_base = parse_float(get_value_by_label_contains(soup, "Base Size") or
                                  get_value_by_label_contains(soup, "Issue Size Base") or
                                  get_value_by_label_contains(soup, "Base Issue Size"))
    issue_size_oversubscription = parse_float(get_value_by_label_contains(soup, "Oversubscription") or
                                             get_value_by_label_contains(soup, "Green Shoe") or
                                             get_value_by_label_contains(soup, "Oversubscription Option"))
    overall_issue_size = parse_float(get_value_by_label_contains(soup, "Overall Issue Size") or
                                     get_value_by_label_contains(soup, "Total Issue Size") or
                                     get_value_by_label_contains(soup, "Issue Size"))
    
    # Extract coupon rates - look for ranges
    coupon_text = get_value_by_label_contains(soup, "Coupon Rate") or \
                 get_value_by_label_contains(soup, "Interest Rate") or \
                 get_value_by_label_contains(soup, "Coupon")
    
    coupon_rate_min = None
    coupon_rate_max = None
    
    if coupon_text:
        # Try to extract range like "8.60% to 8.90%"
        import re
        range_match = re.search(r'(\d+\.?\d*)\s*%\s*to\s*(\d+\.?\d*)%', coupon_text)
        if range_match:
            coupon_rate_min = float(range_match.group(1))
            coupon_rate_max = float(range_match.group(2))
        else:
            # Single value
            coupon_rate_min = parse_float(coupon_text)
            coupon_rate_max = coupon_rate_min
    
    # Extract NCD details
    face_value_per_ncd = parse_float(get_value_by_label_contains(soup, "Face Value") or
                                     get_value_by_label_contains(soup, "NCD Face Value") or
                                     get_value_by_label_contains(soup, "Per NCD"))
    issue_price_per_ncd = parse_float(get_value_by_label_contains(soup, "Issue Price") or
                                      get_value_by_label_contains(soup, "NCD Price"))
    minimum_lot_size_ncd = parse_float(get_value_by_label_contains(soup, "Minimum Lot") or
                                      get_value_by_label_contains(soup, "Lot Size") or
                                      get_value_by_label_contains(soup, "Minimum Investment"))
    market_lot_ncd = minimum_lot_size_ncd  # Usually same as minimum
    
    # Extract exchanges
    exchanges = _extract_exchanges(soup)
    
    # Extract other details
    security_name = get_value_by_label_contains(soup, "Security Name")
    security_type = get_value_by_label_contains(soup, "Security Type")
    basis_of_allotment = get_value_by_label_contains(soup, "Basis of Allotment")
    debenture_trustee = get_value_by_label_contains(soup, "Debenture Trustee")
    
    # Extract complex structures
    coupon_series = _extract_coupon_series(soup)
    ratings = _extract_ratings(soup)
    promoters = _extract_promoters(soup)
    objects_of_issue = _extract_objects_of_issue(soup)
    company_contact = _extract_company_contact(soup)
    registrar = _extract_registrar(soup)
    lead_managers = _extract_lead_managers(soup)
    faqs = _extract_faqs(soup)
    documents = _extract_documents(soup)
    
    # Extract logo
    logo_url = extract_text_by_selector(soup, "img.logo, .company-logo img, .ncd-logo img", "src")
    
    # Update coupon rates from series if available
    if coupon_series:
        rates = [s.get("coupon_percent_pa", 0) for s in coupon_series if s.get("coupon_percent_pa")]
        if rates:
            coupon_rate_min = min(rates)
            coupon_rate_max = max(rates)
    
    data = {
        "slug": slug,
        "issuer": issuer,
        "issue_name": issue_name,
        "logo_url": logo_url,
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
        "company_financials": None,  # TODO: Implement
        "ncd_allocation": None,  # TODO: Implement
        "objects_of_issue": objects_of_issue,
        "company_contact": company_contact,
        "registrar": registrar,
        "lead_managers": lead_managers,
        "documents": documents,
        "faq": faqs,
        "news": [],  # TODO: Implement
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
    """Extract NCD description - improved"""
    # Look for description in various places
    desc_section = (soup.find("div", id=lambda x: x and "description" in x.lower()) or
                   soup.find("div", class_=lambda x: x and "description" in x.lower()) or
                   soup.find("div", class_=lambda x: x and "ncd-summary" in x.lower()))
    
    if desc_section:
        paragraphs = desc_section.find_all("p")
        if paragraphs:
            # Filter out very short paragraphs and navigation
            desc_parts = []
            for p in paragraphs:
                text = clean_text(p.get_text())
                if text and len(text) > 50:  # Meaningful content
                    # Filter out navigation links
                    if not any(keyword in text for keyword in ["Visit Website", "Read more", "Click here"]):
                        desc_parts.append(text)
            
            if desc_parts:
                return clean_text(" ".join(desc_parts[:5]))  # First 5 meaningful paragraphs
    
    # Try to extract from main content area
    main_content = soup.find("main") or soup.find("div", class_=lambda x: x and "content" in x.lower())
    if main_content:
        # Get first few paragraphs that describe the company
        paragraphs = main_content.find_all("p")
        desc_parts = []
        for p in paragraphs[:5]:
            text = clean_text(p.get_text())
            if text and len(text) > 100:  # Substantial content
                desc_parts.append(text)
        
        if desc_parts:
            return clean_text(" ".join(desc_parts))
    
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
    """Improved date extraction with card support and range handling"""
    import re
    
    # Try each label
    for label in labels:
        value = get_value_by_label_contains(soup, label)
        if value:
            # Handle date ranges
            date_pattern = r'([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4})'
            dates = re.findall(date_pattern, value)
            
            if dates:
                if "Close" in label:
                    date_val = parse_date(dates[-1]) if len(dates) > 1 else parse_date(dates[0])
                else:
                    date_val = parse_date(dates[0])
                if date_val:
                    return date_val
            
            date_val = parse_date(value)
            if date_val:
                return date_val
    
    # Try card-based extraction
    for label in labels:
        cards = soup.find_all("div", class_=lambda x: x and "card" in x.lower())
        for card in cards:
            card_text = card.get_text()
            if label.lower() in card_text.lower():
                date_elem = card.find("p", class_=lambda x: x and "fs-5" in x)
                if date_elem:
                    date_text = clean_text(date_elem.get_text())
                    dates = re.findall(r'([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4})', date_text)
                    if dates:
                        if "Close" in label:
                            date_val = parse_date(dates[-1]) if len(dates) > 1 else parse_date(dates[0])
                        else:
                            date_val = parse_date(dates[0])
                        if date_val:
                            return date_val
                    else:
                        date_val = parse_date(date_text)
                        if date_val:
                            return date_val
    
    return None


def _extract_exchanges(soup: BeautifulSoup) -> list:
    """Extract exchange names - improved"""
    exchanges = []
    
    # Try multiple patterns
    exchange_text = (get_value_by_label_contains(soup, "Exchange") or
                    get_value_by_label_contains(soup, "Listing At") or
                    get_value_by_label_contains(soup, "Listed On"))
    
    if exchange_text:
        # Split by comma or common separators
        import re
        parts = re.split(r'[,&]', exchange_text)
        for part in parts:
            clean_part = clean_text(part)
            if clean_part:
                # Normalize exchange names
                if "BSE" in clean_part.upper():
                    exchanges.append("BSE")
                elif "NSE" in clean_part.upper():
                    exchanges.append("NSE")
                elif clean_part not in exchanges:
                    exchanges.append(clean_part)
    
    # Remove duplicates while preserving order
    seen = set()
    return [x for x in exchanges if not (x in seen or seen.add(x))]


def _extract_coupon_series(soup: BeautifulSoup) -> list:
    """Extract coupon series information - improved"""
    series = []
    
    # Look for coupon series table with multiple patterns
    series_table = (soup.find("table", id=lambda x: x and "coupon" in x.lower()) or
                   soup.find("table", class_=lambda x: x and "series" in x.lower()) or
                   soup.find("table", class_=lambda x: x and "coupon" in x.lower()))
    
    if series_table:
        from app.scraper.parser import extract_table_data
        # Try to extract from the specific table
        table_data = extract_table_data(soup, table_id=series_table.get("id")) if series_table.get("id") else extract_table_data(soup)
        
        for row in table_data:
            if row and any(key in str(row).lower() for key in ["series", "coupon", "tenor", "frequency"]):
                series_info = {
                    "series_name": row.get("Series", row.get("Series Name", "")),
                    "frequency_of_interest_payment": row.get("Frequency", row.get("Frequency of Interest", "")),
                    "nature": row.get("Nature", ""),
                    "tenor": row.get("Tenor", row.get("Tenure", "")),
                    "coupon_percent_pa": parse_float(row.get("Coupon Rate", row.get("Coupon %", ""))) or 0,
                    "effective_yield_percent_pa": parse_float(row.get("Effective Yield", row.get("Yield", ""))) or 0,
                    "amount_on_maturity": parse_float(row.get("Amount on Maturity", row.get("Maturity Amount", ""))) or 0,
                }
                # Only add if we have meaningful data
                if series_info["series_name"] or series_info["coupon_percent_pa"]:
                    series.append(series_info)
    
    return series


def _extract_ratings(soup: BeautifulSoup) -> list:
    """Extract rating information - improved"""
    ratings = []
    
    # Look for ratings section
    rating_section = (extract_section_by_heading(soup, "Rating") or
                     extract_section_by_heading(soup, "Credit Rating") or
                     soup.find("div", id=lambda x: x and "rating" in x.lower()))
    
    if rating_section:
        rating_text = rating_section.get_text()
        import re
        
        # Try to find rating agency names with their ratings
        agencies = ["CARE", "ICRA", "CRISIL", "India Ratings", "Brickwork"]
        
        for agency in agencies:
            if agency in rating_text:
                # Pattern: Agency name followed by rating like "CARE AA-/(Stable)"
                pattern = rf'{agency}[^A-Z]*([A-Z]+\+?\-?/?[A-Z]*)\s*\(?([^)]*)\)?'
                match = re.search(pattern, rating_text)
                
                if match:
                    rating_value = match.group(1)
                    outlook_text = match.group(2) if len(match.groups()) > 1 else ""
                    
                    ratings.append({
                        "rating_agency": agency,
                        "ncd_rating": rating_value,
                        "outlook": clean_text(outlook_text),
                        "safety_degree": "",
                        "risk_degree": "",
                    })
        
        # If no structured match, try simple pattern
        if not ratings:
            rating_pattern = r'([A-Z]+\+?\-?/?[A-Z]*)'
            matches = re.findall(rating_pattern, rating_text)
            # Filter valid ratings (usually 1-4 characters like AA, AAA, AA-)
            valid_ratings = [m for m in matches if 1 <= len(m) <= 5 and m.isupper()]
            if valid_ratings:
                # Try to associate with agencies found in text
                for agency in agencies:
                    if agency in rating_text:
                        ratings.append({
                            "rating_agency": agency,
                            "ncd_rating": valid_ratings[0],
                            "outlook": "",
                            "safety_degree": "",
                            "risk_degree": "",
                        })
                        break
    
    return ratings


def _extract_promoters(soup: BeautifulSoup) -> list:
    """Extract promoters"""
    promoters = []
    promoter_text = get_value_by_label_contains(soup, "Promoters")
    if promoter_text:
        import re
        parts = re.split(r'[,;]|and\s+', promoter_text)
        promoters = [clean_text(part) for part in parts if clean_text(part)]
    return promoters


def _extract_objects_of_issue(soup: BeautifulSoup) -> list:
    """Extract objects of issue"""
    objects = []
    section = extract_section_by_heading(soup, "Objects") or \
              extract_section_by_heading(soup, "Objects of the Issue")
    
    if section:
        items = section.find_all("li")
        for item in items:
            text = clean_text(item.get_text())
            if text:
                objects.append(text)
    
    return objects


def _extract_company_contact(soup: BeautifulSoup) -> Optional[dict]:
    """Extract company contact information - improved"""
    contact_section = extract_section_by_heading(soup, "Contact") or \
                     extract_section_by_heading(soup, "Company Contact") or \
                     soup.find("div", id=lambda x: x and "contact" in x.lower())
    
    if contact_section:
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
        
        # Extract company name
        name_elem = contact_section.find("strong")
        if name_elem:
            contact["company_name"] = clean_text(name_elem.get_text())
        
        # Extract address from divs
        address_divs = contact_section.find_all("div")
        address_parts = []
        for div in address_divs:
            text = clean_text(div.get_text())
            # Filter out contact info, keep only address
            if text and len(text) > 5 and len(text) < 100:
                if not any(char in text for char in ["@", "http", "www"]) and \
                   not any(keyword in text for keyword in ["Visit Website", "Phone", "Email"]):
                    if text != contact["company_name"]:
                        address_parts.append(text)
        
        if address_parts:
            contact["address_line_1"] = address_parts[0] if address_parts else ""
            # Try to extract city, state, pincode from last part
            if len(address_parts) > 1:
                last_part = address_parts[-1]
                import re
                pincode_match = re.search(r'\d{6}', last_part)
                if pincode_match:
                    contact["pincode"] = pincode_match.group()
                    parts = last_part.split(",")
                    if len(parts) >= 2:
                        contact["city"] = parts[0].strip()
                        contact["state"] = parts[1].replace(contact["pincode"], "").strip()
        
        # Extract phone, email, website from list items with icons
        for li in contact_section.find_all("li"):
            icon = li.find("i", class_=lambda x: x)
            icon_class = " ".join(icon.get("class", [])) if icon else ""
            
            text = clean_text(li.get_text())
            link = li.find("a", href=True)
            
            if "envelope" in icon_class or "@" in text:
                # Email
                if "@" in text:
                    contact["email"] = text
                elif link and "mailto:" in link.get("href", ""):
                    contact["email"] = link.get("href").replace("mailto:", "")
            elif "phone" in icon_class:
                # Phone
                import re
                phone_match = re.search(r'[\d\s\+\-\(\)]+', text)
                if phone_match:
                    phone = phone_match.group().strip()
                    if len(phone) >= 8:
                        contact["phone_numbers"].append(phone)
            elif "globe" in icon_class or link:
                # Website
                if link:
                    href = link.get("href", "")
                    if href.startswith("http"):
                        contact["website"] = href
        
        if contact["company_name"] or contact["address_line_1"]:
            return contact
    
    return None


def _extract_registrar(soup: BeautifulSoup) -> Optional[dict]:
    """Extract registrar information - improved"""
    registrar_section = extract_section_by_heading(soup, "Registrar") or \
                       extract_section_by_heading(soup, "NCD Registrar") or \
                       soup.find("div", id=lambda x: x and "registrar" in x.lower())
    
    if registrar_section:
        registrar = {
            "name": "",
            "phone_numbers": [],
            "email": "",
            "website": "",
        }
        
        # Extract name - try multiple patterns
        name_elem = (registrar_section.find("strong") or
                    registrar_section.find("a", class_=lambda x: x and "registrar" in x.lower()) or
                    registrar_section.find("p"))
        
        if name_elem:
            name_text = clean_text(name_elem.get_text())
            if "Visit" not in name_text and len(name_text) > 3:
                registrar["name"] = name_text
        
        # Extract contact info from list items with icons
        for li in registrar_section.find_all("li"):
            icon = li.find("i", class_=lambda x: x)
            icon_class = " ".join(icon.get("class", [])) if icon else ""
            
            text = clean_text(li.get_text())
            link = li.find("a", href=True)
            
            if "envelope" in icon_class or "@" in text:
                # Email
                if "@" in text:
                    registrar["email"] = text
                elif link and "mailto:" in link.get("href", ""):
                    registrar["email"] = link.get("href").replace("mailto:", "")
            elif "phone" in icon_class:
                # Phone
                import re
                phone_match = re.search(r'[\d\s\+\-\(\)]+', text)
                if phone_match:
                    phone = phone_match.group().strip()
                    if len(phone) >= 8:
                        registrar["phone_numbers"].append(phone)
            elif "globe" in icon_class or link:
                # Website
                if link:
                    href = link.get("href", "")
                    if href.startswith("http"):
                        registrar["website"] = href
        
        if registrar["name"]:
            return registrar
    
    return None


def _extract_lead_managers(soup: BeautifulSoup) -> list:
    """Extract lead managers - filters out report links"""
    lead_managers = []
    
    # Filter keywords that indicate report/navigation links
    exclude_keywords = [
        "List of Issues", "No. of Issues", "Performance", "Report",
        "Market Maker", "Registrar", "Broker Report", "IPO Report"
    ]
    
    # Look for lead manager section
    lm_section = extract_section_by_heading(soup, "Lead Manager") or \
                 extract_section_by_heading(soup, "NCD Lead Manager")
    
    if lm_section:
        # Try ordered list (most reliable)
        ol = lm_section.find("ol")
        if ol:
            for li in ol.find_all("li"):
                text = clean_text(li.get_text())
                # Filter out report links
                if text and not any(keyword in text for keyword in exclude_keywords):
                    # Extract company name (before parentheses or special markers)
                    if "(" in text:
                        text = text.split("(")[0].strip()
                    if text and len(text) > 3:
                        lead_managers.append(text)
        else:
            # Try links - filter carefully
            links = lm_section.find_all("a")
            for link in links:
                text = clean_text(link.get_text())
                href = link.get("href", "")
                # Only add if it's a lead manager review link, not a report link
                if text and "/lead-manager-review/" in href:
                    if not any(keyword in text for keyword in exclude_keywords):
                        lead_managers.append(text)
    
    return lead_managers


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
