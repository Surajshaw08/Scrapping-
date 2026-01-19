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
    extract_all_text_by_selector,
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
        data = scrape_ipo_from_file("html_cache/12345.html")
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


def _scrape_ipo_from_soup(soup: BeautifulSoup, url: str) -> dict:
    """Internal function to scrape from BeautifulSoup object"""
    # Basic information
    name_elem = soup.find("h1")
    name = name_elem.get_text(strip=True) if name_elem else ""
    external_id = int(url.rstrip("/").split("/")[-1])
    slug = url.split("/ipo/")[1].split("/")[0] if "/ipo/" in url else ""
    
    # Get status for isTentative check
    status = get_value_by_label_contains(soup, "Status") or ""

    # Extract all data fields
    data = {
        "external_id": external_id,
        "slug": slug,
        "name": name,
        "category": "IPO",
        "exchange": get_value_by_label_contains(soup, "Exchange") or "BSE & NSE",

        # Issue details
        "issue_size_crore": parse_float(
            get_value_by_label_contains(soup, "Issue Size")
        ),
        "fresh_issue_crore": parse_float(
            get_value_by_label_contains(soup, "Fresh Issue")
        ),
        "ofs_issue_crore": parse_float(
            get_value_by_label_contains(soup, "Offer for Sale")
        ),
        "market_maker_reserved_crore": parse_float(
            get_value_by_label_contains(soup, "Market Maker")
        ),
        "face_value": parse_float(
            get_value_by_label_contains(soup, "Face Value")
        ),
        "issue_type": get_value_by_label_contains(soup, "Issue Type"),
        
        # Price details
        "issue_price_low": parse_float(
            get_value_by_label_contains(soup, "Price Band")
        ),
        "issue_price_high": parse_float(
            get_value_by_label_contains(soup, "Price Band")
        ),
        "lot_size": parse_int(
            get_value_by_label_contains(soup, "Lot Size")
        ),
        "single_lot_price": parse_float(
            get_value_by_label_contains(soup, "Lot Investment")
        ),
        "small_hni_lot": parse_int(
            get_value_by_label_contains(soup, "Small HNI")
        ),
        "big_hni_lot": parse_int(
            get_value_by_label_contains(soup, "Big HNI")
        ),

        # Dates - try multiple patterns and card-based extraction
        "issue_open_date": _extract_date(soup, ["Issue Open", "IPO Open", "Open Date", "Issue Open Date"]),
        "issue_close_date": _extract_date(soup, ["Issue Close", "IPO Close", "Close Date", "Issue Close Date"]),
        "allotment_date": _extract_date(soup, ["Allotment", "Allotment Date", "Basis of Allotment"]),
        "refund_date": _extract_date(soup, ["Refund", "Refund Date"]),
        "listing_date": _extract_date(soup, ["Listing Date", "Listing", "Tentative Listing Date"]),
        "boa_date": _extract_date(soup, ["Basis of Allotment", "BOA", "BOA Date"]),
        "cos_date": _extract_date(soup, ["Credit of Shares", "COS", "Credit Date"]),

        # Company details
        "website": extract_link_by_text(soup, "Website") or \
                  get_value_by_label_contains(soup, "Website"),
        "sector": _extract_sector(soup),
        "bse_code": get_value_by_label_contains(soup, "BSE Code"),
        "nse_code": get_value_by_label_contains(soup, "NSE Code"),
        
        # Promoter holding
        "promoter_holding_pre": parse_float(
            get_value_by_label_contains(soup, "Promoter Holding")
        ),
        "promoter_holding_post": parse_float(
            get_value_by_label_contains(soup, "Post Issue")
        ),

        # Lists and sections
        "about_company": _extract_about_company(soup),
        "strengths": _extract_strengths(soup),
        "weaknesses": _extract_weaknesses(soup),
        "opportunities": _extract_opportunities(soup),
        "threats": _extract_threats(soup),
        "products": _extract_products(soup),
        "services": _extract_services(soup),
        "promoters": _extract_promoters(soup),
        "lead_managers": _extract_lead_managers(soup),
        
        # Complex data structures (to be implemented)
        "objectives": _extract_objectives(soup),
        "financials": _extract_financials(soup),
        "peers": _extract_peers(soup),
        "company_contacts": _extract_company_contacts(soup),
        "registrar": _extract_registrar(soup),
        "reservations": _extract_reservations(soup),
        "rhp_insights": _extract_rhp_insights(soup),

        # URLs
        "drhp_url": extract_link_by_text(soup, "DRHP"),
        "rhp_url": extract_link_by_text(soup, "RHP"),
        "final_prospectus_url": extract_link_by_text(soup, "Final Prospectus"),
        "anchor_list_url": extract_link_by_text(soup, "Anchor"),
        "logo_url": extract_text_by_selector(soup, "img.logo, .company-logo img", "src"),

        # Other
        "isTentative": "Tentative" in name or "Tentative" in status,
        "rating": parse_float(get_value_by_label_contains(soup, "Rating")),
        "listing_price": parse_float(get_value_by_label_contains(soup, "Listing Price")),

        # FAQs
        "faqs": extract_faqs(soup),
    }

    return data


def _extract_about_company(soup: BeautifulSoup) -> list:
    """Extract about company section - filters out navigation links"""
    about = []
    
    # Try multiple patterns
    section = (extract_section_by_heading(soup, "About") or 
               extract_section_by_heading(soup, "Company Overview") or
               soup.find("div", id="about-company-section") or
               soup.find("div", id="ipoSummary"))
    
    if section:
        # Filter out navigation links and unrelated content
        exclude_keywords = [
            "IPO Reports", "eBook", "IPO Articles", "IPO Message Board",
            "IPO Guide", "Broker", "Review", "Report", "Compare",
            "Angel One", "Kotak Securities", "Motilal Oswal", "Zerodha",
            "Upstox", "5Paisa", "More Brokers", "List of", "Performance"
        ]
        
        # Extract from list items
        items = section.find_all("li")
        if items:
            for li in items:
                text = clean_text(li.get_text())
                # Skip if it's a navigation link
                if text and not any(keyword in text for keyword in exclude_keywords):
                    # Check if it's actually a link to reports/articles
                    link = li.find("a", href=True)
                    if not link or "/report/" not in link.get("href", ""):
                        if len(text) > 20:  # Meaningful content
                            about.append(text)
        
        # If no list items, extract from paragraphs
        if not about:
            paragraphs = section.find_all("p")
            for p in paragraphs:
                text = clean_text(p.get_text())
                # Filter meaningful content, exclude navigation
                if text and len(text) > 30 and not any(keyword in text for keyword in exclude_keywords):
                    about.append(text)
    
    return about


def _extract_strengths(soup: BeautifulSoup) -> list:
    """Extract strengths section"""
    strengths = []
    
    # Try multiple heading patterns
    section = (extract_section_by_heading(soup, "Strengths") or
               extract_section_by_heading(soup, "Strength") or
               soup.find("div", id=lambda x: x and "strength" in x.lower()))
    
    if section:
        strengths = extract_list(section)
        # If no list, try paragraphs
        if not strengths:
            for p in section.find_all("p"):
                text = clean_text(p.get_text())
                if text:
                    strengths.append(text)
    
    return strengths


def _extract_weaknesses(soup: BeautifulSoup) -> list:
    """Extract weaknesses section"""
    weaknesses = []
    
    section = (extract_section_by_heading(soup, "Weaknesses") or
               extract_section_by_heading(soup, "Weakness") or
               soup.find("div", id=lambda x: x and "weakness" in x.lower()))
    
    if section:
        weaknesses = extract_list(section)
        if not weaknesses:
            for p in section.find_all("p"):
                text = clean_text(p.get_text())
                if text:
                    weaknesses.append(text)
    
    return weaknesses


def _extract_opportunities(soup: BeautifulSoup) -> list:
    """Extract opportunities section"""
    opportunities = []
    
    section = (extract_section_by_heading(soup, "Opportunities") or
               extract_section_by_heading(soup, "Opportunity") or
               soup.find("div", id=lambda x: x and "opportunity" in x.lower()))
    
    if section:
        opportunities = extract_list(section)
        if not opportunities:
            for p in section.find_all("p"):
                text = clean_text(p.get_text())
                if text:
                    opportunities.append(text)
    
    return opportunities


def _extract_threats(soup: BeautifulSoup) -> list:
    """Extract threats section"""
    threats = []
    
    section = (extract_section_by_heading(soup, "Threats") or
               extract_section_by_heading(soup, "Threat") or
               soup.find("div", id=lambda x: x and "threat" in x.lower()))
    
    if section:
        threats = extract_list(section)
        if not threats:
            for p in section.find_all("p"):
                text = clean_text(p.get_text())
                if text:
                    threats.append(text)
    
    return threats


def _extract_products(soup: BeautifulSoup) -> list:
    """Extract products section"""
    products = []
    
    section = (extract_section_by_heading(soup, "Products") or
               extract_section_by_heading(soup, "Product") or
               soup.find("div", id=lambda x: x and "product" in x.lower()))
    
    if section:
        products = extract_list(section)
        if not products:
            for p in section.find_all("p"):
                text = clean_text(p.get_text())
                if text:
                    products.append(text)
    
    return products


def _extract_services(soup: BeautifulSoup) -> list:
    """Extract services section - filters out broker names"""
    services = []
    
    section = (extract_section_by_heading(soup, "Services") or
               extract_section_by_heading(soup, "Service") or
               soup.find("div", id=lambda x: x and "service" in x.lower()))
    
    if section:
        # Filter out broker names and navigation
        exclude_keywords = [
            "Broker", "Zerodha", "Angel One", "Kotak", "Motilal", "Upstox",
            "5Paisa", "Indiabulls", "More Brokers", "Report", "Review"
        ]
        
        items = section.find_all("li")
        if items:
            for li in items:
                text = clean_text(li.get_text())
                if text and not any(keyword in text for keyword in exclude_keywords):
                    services.append(text)
        
        if not services:
            for p in section.find_all("p"):
                text = clean_text(p.get_text())
                if text and not any(keyword in text for keyword in exclude_keywords):
                    services.append(text)
    
    # Also check in about section for service mentions (but filter carefully)
    if not services:
        about_section = soup.find("div", id="ipoSummary") or soup.find("div", id="about-company-section")
        if about_section:
            text = about_section.get_text()
            if "service" in text.lower() and "broker" not in text.lower():
                # Extract sentences mentioning services
                import re
                sentences = re.split(r'[.!?]\s+', text)
                for sentence in sentences:
                    if "service" in sentence.lower() and len(sentence) > 20:
                        clean_sent = clean_text(sentence)
                        if not any(keyword in clean_sent for keyword in exclude_keywords):
                            services.append(clean_sent)
    
    return services


def _extract_promoters(soup: BeautifulSoup) -> list:
    """Extract promoters section"""
    promoters = []
    
    # Method 1: From section heading
    section = (extract_section_by_heading(soup, "Promoters") or
               extract_section_by_heading(soup, "Promoter") or
               soup.find("div", id=lambda x: x and "promoter" in x.lower()))
    
    if section:
        promoters = extract_list(section)
        if not promoters:
            # Try paragraphs
            for p in section.find_all("p"):
                text = clean_text(p.get_text())
                if text:
                    promoters.append(text)
            # Try divs
            if not promoters:
                for div in section.find_all("div"):
                    text = clean_text(div.get_text())
                    if text and len(text) > 10 and len(text) < 200:
                        promoters.append(text)
    
    # Method 2: From table value
    if not promoters:
        promoter_text = get_value_by_label_contains(soup, "Promoters")
        if promoter_text:
            # Split by common separators
            import re
            parts = re.split(r'[,;]\s*|and\s+', promoter_text)
            promoters = [clean_text(part) for part in parts if clean_text(part)]
    
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
    """Extract IPO objectives - returns empty list if can't parse properly"""
    # For now, return empty list as objectives need structured data (sno, description, amount_crore)
    # This would require parsing a specific table structure that may not exist
    return []


def _extract_financials(soup: BeautifulSoup) -> list:
    """Extract financial data - returns empty list if can't parse properly"""
    # Financial table structure is complex and needs proper parsing
    # For now, return empty list to avoid validation errors
    # TODO: Implement proper financial table parsing with date conversion
    return []


def _extract_peers(soup: BeautifulSoup) -> list:
    """Extract peer analysis data - returns empty list if can't parse properly"""
    # Peer table needs specific structure (company, eps_basic, eps_diluted, nav, pe, ronw)
    # For now, return empty list to avoid validation errors
    # TODO: Implement proper peer table parsing
    return []


def _extract_company_contacts(soup: BeautifulSoup) -> list:
    """Extract company contact information"""
    contacts = []
    
    # Look for contact details section
    contact_section = extract_section_by_heading(soup, "Contact Details") or \
                     soup.find("div", id=lambda x: x and "contact" in x.lower())
    
    if contact_section:
        # Extract address, phone, email, website
        contact_info = {
            "name": "",
            "address": "",
            "phone": "",
            "email": "",
            "website": ""
        }
        
        # Extract company name
        name_elem = contact_section.find("strong")
        if name_elem:
            contact_info["name"] = clean_text(name_elem.get_text()).replace(" Address", "").strip()
        
        # Extract address
        address_divs = contact_section.find_all("div")
        address_parts = []
        for div in address_divs:
            text = clean_text(div.get_text())
            if text and len(text) > 5 and len(text) < 100 and not any(char in text for char in ["@", "http", "www"]):
                address_parts.append(text)
        
        if address_parts:
            contact_info["address"] = ", ".join(address_parts[:3])  # First 3 parts
        
        # Extract phone, email, website from list items with icons
        for li in contact_section.find_all("li"):
            icon = li.find("i", class_=lambda x: x)
            icon_class = " ".join(icon.get("class", [])) if icon else ""
            
            text = clean_text(li.get_text())
            link = li.find("a", href=True)
            
            if "envelope" in icon_class or "@" in text:
                # Email
                if "@" in text:
                    contact_info["email"] = text
                elif link and "mailto:" in link.get("href", ""):
                    contact_info["email"] = link.get("href").replace("mailto:", "")
            elif "phone" in icon_class or "call" in icon_class:
                # Phone - extract numbers
                import re
                phone_match = re.search(r'[\d\s\+\-\(\)]+', text)
                if phone_match:
                    phone = phone_match.group().strip()
                    if len(phone) >= 8:
                        contact_info["phone"] = phone
            elif "globe" in icon_class or "external-link" in icon_class or link:
                # Website
                if link:
                    href = link.get("href", "")
                    if href.startswith("http"):
                        contact_info["website"] = href
                    elif "Visit Website" in text and link:
                        contact_info["website"] = href
        
        # Only add if we have meaningful data
        if contact_info["address"] or contact_info["email"] or contact_info["name"]:
            contacts.append(contact_info)
    
    return contacts


def _extract_registrar(soup: BeautifulSoup) -> Optional[dict]:
    """Extract registrar information - improved extraction"""
    registrar_section = extract_section_by_heading(soup, "Registrar") or \
                        extract_section_by_heading(soup, "IPO Registrar") or \
                        soup.find("div", id=lambda x: x and "registrar" in x.lower())
    
    if registrar_section:
        registrar = {
            "name": "",
            "phone_numbers": [],
            "email": "",
            "website": ""
        }
        
        # Extract name - try multiple patterns
        name_elem = (registrar_section.find("a", class_=lambda x: x and "registrar-name" in x) or
                    registrar_section.find("p", class_=lambda x: x and "registrar-name" in x) or
                    registrar_section.find("strong") or
                    registrar_section.find("p"))
        
        if name_elem:
            name_text = clean_text(name_elem.get_text())
            # Filter out "Visit Website" and similar
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
                # Phone - extract numbers
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


def _extract_reservations(soup: BeautifulSoup) -> list:
    """Extract reservation percentages - returns empty list if can't parse properly"""
    # Reservation table needs specific structure (qib, anchor, ex_anchor, nii, etc.)
    # The extract_table_data is picking up wrong tables (IPO details table)
    # For now, return empty list to avoid validation errors
    # TODO: Implement proper reservation table parsing with correct table identification
    return []


def _extract_date(soup: BeautifulSoup, labels: list):
    """Extract date using multiple label patterns - improved to handle date ranges"""
    from app.utils.normalizers import parse_date
    from datetime import date
    import re
    
    # Try each label
    for label in labels:
        value = get_value_by_label_contains(soup, label)
        if value:
            # Handle date ranges like "Fri, Jan 9, 2026 and closes on Tue, Jan 13, 2026"
            # Extract first date for open, second for close
            date_pattern = r'([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4})'
            dates = re.findall(date_pattern, value)
            
            if dates:
                # For open date, take first; for close date, take last
                if "Open" in label or "Open Date" in label:
                    date_val = parse_date(dates[0])
                elif "Close" in label or "Close Date" in label:
                    date_val = parse_date(dates[-1]) if len(dates) > 1 else parse_date(dates[0])
                else:
                    date_val = parse_date(dates[0])
                
                if date_val:
                    return date_val
            
            # Try parsing the value directly
            date_val = parse_date(value)
            if date_val:
                return date_val
    
    # Try extracting from card elements (common on chittorgarh)
    for label in labels:
        # Look for cards with the label
        cards = soup.find_all("div", class_=lambda x: x and "card" in x.lower())
        for card in cards:
            # Check if card contains the label
            card_text = card.get_text()
            if label.lower() in card_text.lower():
                # Look for date in the card
                date_elem = card.find("p", class_=lambda x: x and "fs-5" in x) or \
                           card.find("p", class_=lambda x: x and "date" in x.lower())
                if date_elem:
                    date_text = clean_text(date_elem.get_text())
                    # Handle date ranges in cards
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
    
    # Try extracting from IPO Date table field (might have ranges like "20 to 22 Jan, 2026")
    if "Open" in str(labels) or "Close" in str(labels):
        ipo_date_value = get_value_by_label_contains(soup, "IPO Date")
        if ipo_date_value:
            # Pattern 1: "20 to 22 Jan, 2026"
            range_match = re.search(r'(\d{1,2})\s+to\s+(\d{1,2})\s+([A-Za-z]{3}),\s+(\d{4})', ipo_date_value)
            if range_match:
                day1, day2, month, year = range_match.groups()
                if "Close" in str(labels) or "Close Date" in str(labels):
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
                if "Close" in str(labels) or "Close Date" in str(labels):
                    date_str = f"{month2} {day2}, {year2}"
                else:
                    date_str = f"{month1} {day1}, {year1}"
                date_val = parse_date(date_str)
                if date_val:
                    return date_val
    
    return None


def _extract_sector(soup: BeautifulSoup) -> Optional[str]:
    """Extract sector information"""
    sector = get_value_by_label_contains(soup, "Sector")
    if sector:
        return sector
    
    # Try to find in company description or about section
    about_section = soup.find("div", id="ipoSummary") or soup.find("div", id="about-company-section")
    if about_section:
        text = about_section.get_text()
        # Look for common sector keywords
        sectors = ["Energy", "Technology", "Finance", "Healthcare", "Manufacturing", 
                  "Logistics", "Infrastructure", "Real Estate", "Telecom", "FMCG"]
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
