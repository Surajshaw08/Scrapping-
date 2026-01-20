from bs4 import BeautifulSoup, Tag
from typing import Optional, List
import json
import re
from app.utils.helpers import clean_text


def get_value_by_label_contains(soup: BeautifulSoup, label: str) -> Optional[str]:
    """
    Finds table value where <td> contains label text
    Example: 'Issue Size (₹ Cr)' contains 'Issue Size'
    """
    for td in soup.find_all("td"):
        if label.lower() in td.get_text(strip=True).lower():
            next_td = td.find_next_sibling("td")
            return clean_text(next_td.get_text()) if next_td else None
    return None


def get_value_by_label_in_li(soup: BeautifulSoup, label: str, list_class: str = "top-ratios") -> Optional[str]:
    """
    Finds value in ul.top-ratios (or similar) where <li> has two <span>s:
    first contains label, second (or span.text-end) contains value.
    Used on chittorgarh NCD/IPO detail pages.
    """
    ul = soup.find("ul", class_=lambda x: x and list_class in (x if isinstance(x, str) else " ".join(x or [])))
    if not ul:
        return None
    for li in ul.find_all("li"):
        spans = li.find_all("span")
        for s in spans:
            if label.lower() in clean_text(s.get_text()).lower():
                val_span = li.find("span", class_=lambda x: x and "text-end" in (x if isinstance(x, str) else " ".join(x or [])))
                if val_span:
                    return clean_text(val_span.get_text())
                if len(spans) >= 2:
                    return clean_text(spans[-1].get_text())
                return None
    return None


def get_value_from_cards(soup: BeautifulSoup, label: str) -> Optional[str]:
    """
    Finds value in card-ipo layout: p.text-muted (label) + p.fs-5 (value).
    Used for Open Date, Close Date, Issue Size (Overall), Coupon Rate, etc.
    """
    for p in soup.find_all("p", class_=lambda c: c and "text-muted" in (c if isinstance(c, str) else " ".join(c or []) or "").lower()):
        if label.lower() in clean_text(p.get_text()).lower():
            next_p = p.find_next_sibling("p")
            if next_p:
                return clean_text(next_p.get_text())
            parent = p.parent
            if parent:
                fs5 = parent.find("p", class_=lambda c: c and "fs-5" in (c if isinstance(c, str) else " ".join(c or []) or "").lower())
                if fs5:
                    return clean_text(fs5.get_text())
    return None


def parse_registrar_info_ul(ul) -> dict:
    """
    Parse ul.registrar-info or similar: li with fa-phone, fa-envelope, fa-globe.
    Returns dict: phone_numbers (list), email, website.
    Handles comma-separated phone numbers in one li.
    """
    out = {"phone_numbers": [], "email": "", "website": ""}
    if not ul:
        return out
    for li in ul.find_all("li"):
        icon = li.find("i", class_=lambda c: c)
        icon_c = " ".join(icon.get("class", [])) if icon else ""
        text = clean_text(li.get_text())
        link = li.find("a", href=True)
        if "envelope" in icon_c or "@" in text:
            out["email"] = text if "@" in text else (link.get("href", "").replace("mailto:", "") if link and "mailto:" in (link.get("href") or "") else out["email"])
        elif "phone" in icon_c:
            for part in [p.strip() for p in text.split(",")]:
                m = re.search(r"[\d\s\+\-\(\)]+", part)
                if m and len(m.group().strip()) >= 8:
                    out["phone_numbers"].append(m.group().strip())
        elif "globe" in icon_c or link:
            if link:
                h = link.get("href", "")
                if h.startswith("http"):
                    out["website"] = h
    return out


def find_card_by_heading(soup: BeautifulSoup, *headings: str):
    """
    Finds a card/section that contains an h2 with any of the given heading texts.
    Returns the parent element that contains both the h2 and the section content
    (e.g. div.card or the h2's parent), or None.
    """
    for h in soup.find_all(["h2", "h3"], class_=lambda c: True):
        t = clean_text(h.get_text()).lower()
        if any(hd.lower() in t for hd in headings):
            # Prefer parent that has both the header and substantial content (address, ol, ul, table)
            p = h.parent
            while p and p.name != "body":
                if p.find("address") or p.find("ol") or p.find("ul", class_=lambda c: c and "registrar" in (c if isinstance(c, str) else " ".join(c or []))) or p.find("table"):
                    return p
                p = p.parent
            return h.parent
    return None


def get_value_by_label_exact(soup: BeautifulSoup, label: str) -> Optional[str]:
    """
    Finds table value where <td> exactly matches label text
    """
    for td in soup.find_all("td"):
        if td.get_text(strip=True).lower() == label.lower():
            next_td = td.find_next_sibling("td")
            return clean_text(next_td.get_text()) if next_td else None
    return None


def extract_list(section: Optional[Tag]) -> List[str]:
    """Extract list items from a section"""
    if not section:
        return []
    return [clean_text(li.get_text()) for li in section.find_all("li")]


def extract_table_data(soup: BeautifulSoup, table_id: Optional[str] = None, 
                      table_class: Optional[str] = None) -> List[dict]:
    """
    Extract data from a table as list of dictionaries.
    First row is treated as headers.
    """
    table = None
    if table_id:
        table = soup.find("table", id=table_id)
    elif table_class:
        table = soup.find("table", class_=table_class)
    else:
        table = soup.find("table")
    
    if not table:
        return []
    
    rows = table.find_all("tr")
    if not rows:
        return []
    
    # Get headers from first row
    headers = [clean_text(th.get_text()) for th in rows[0].find_all(["th", "td"])]
    
    # Extract data rows
    data = []
    for row in rows[1:]:
        cells = [clean_text(td.get_text()) for td in row.find_all("td")]
        if cells:
            row_data = dict(zip(headers, cells))
            data.append(row_data)
    
    return data


def extract_text_by_selector(soup: BeautifulSoup, selector: str, 
                            attribute: Optional[str] = None) -> Optional[str]:
    """
    Extract text or attribute value by CSS selector.
    
    Args:
        soup: BeautifulSoup object
        selector: CSS selector (e.g., "h1.title", "#id", ".class")
        attribute: If provided, extract attribute value instead of text
    
    Returns:
        Text or attribute value, None if not found
    """
    element = soup.select_one(selector)
    if not element:
        return None
    
    if attribute:
        return element.get(attribute, None)
    return clean_text(element.get_text())


def extract_all_text_by_selector(soup: BeautifulSoup, selector: str) -> List[str]:
    """Extract all text from elements matching CSS selector"""
    elements = soup.select(selector)
    return [clean_text(el.get_text()) for el in elements]


def extract_link_by_text(soup: BeautifulSoup, link_text: str, 
                        partial: bool = True) -> Optional[str]:
    """
    Extract href from a link containing specific text.
    
    Args:
        soup: BeautifulSoup object
        link_text: Text to search for in link
        partial: If True, match partial text
    
    Returns:
        URL if found, None otherwise
    """
    for link in soup.find_all("a", href=True):
        text = clean_text(link.get_text())
        if (partial and link_text.lower() in text.lower()) or \
           (not partial and text.lower() == link_text.lower()):
            return link.get("href")
    return None


def extract_section_by_heading(soup: BeautifulSoup, heading_text: str) -> Optional[Tag]:
    """
    Extract a section that follows a specific heading.
    
    Args:
        soup: BeautifulSoup object
        heading_text: Text of the heading to find
    
    Returns:
        The section element following the heading, None if not found
    """
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        if heading_text.lower() in clean_text(heading.get_text()).lower():
            # Find the next sibling section or div
            next_sibling = heading.find_next_sibling()
            if next_sibling:
                return next_sibling
            # Or find parent's next sibling
            parent = heading.parent
            if parent:
                return parent.find_next_sibling()
    return None


def extract_faqs(soup: BeautifulSoup) -> List[dict]:
    """
    Extract FAQ questions and answers.
    Looks for common FAQ patterns including accordion-style FAQs.
    """
    faqs = []
    
    # Method 1: Look for accordion-style FAQs (common on chittorgarh)
    accordion_items = soup.find_all("div", class_=lambda x: x and "accordion-item" in x)
    for item in accordion_items:
        # Check if it has schema.org Question/Answer structure
        if item.get("itemType") == "https://schema.org/Question" or \
           item.find(attrs={"itemType": "https://schema.org/Question"}):
            # Find question
            question_elem = item.find(attrs={"itemProp": "name"}) or \
                          item.find("button", class_=lambda x: x and "accordion-button" in x) or \
                          item.find("h6")
            
            # Find answer
            answer_elem = item.find(attrs={"itemType": "https://schema.org/Answer"}) or \
                        item.find("div", class_=lambda x: x and "accordion-body" in x)
            
            if question_elem and answer_elem:
                question = clean_text(question_elem.get_text())
                answer = clean_text(answer_elem.get_text())
                
                # Only add if it looks like a FAQ (has question mark or is substantial)
                if question and answer and ("?" in question or len(question) > 10):
                    faqs.append({"question": question, "answers": answer})
    
    # Method 2: Try to find FAQ section by heading (if accordion method didn't work)
    if not faqs:
        faq_section = extract_section_by_heading(soup, "FAQ") or \
                      extract_section_by_heading(soup, "Frequently Asked Questions") or \
                      soup.find("div", id=lambda x: x and "faq" in x.lower()) or \
                      soup.find("section", id=lambda x: x and "faq" in x.lower())
        
        if faq_section:
            # Look for question-answer pairs in various formats
            # Try accordion items within the section
            section_accordions = faq_section.find_all("div", class_=lambda x: x and "accordion-item" in x)
            for item in section_accordions:
                question_elem = item.find(["h3", "h4", "h5", "h6", "strong", "b", "button"])
                answer_elem = item.find(["p", "div", "li"], class_=lambda x: x and "accordion-body" in x) or \
                            question_elem.find_next(["p", "div"])
                
                if question_elem and answer_elem:
                    question = clean_text(question_elem.get_text())
                    answer = clean_text(answer_elem.get_text())
                    if question and answer and ("?" in question or len(question) > 10):
                        faqs.append({"question": question, "answers": answer})
            
            # If still no FAQs, try simple heading-based approach
            if not faqs:
                questions = faq_section.find_all(["h3", "h4", "h5", "h6", "strong", "b"])
                for q in questions:
                    question = clean_text(q.get_text())
                    if "?" in question or len(question) > 10:
                        # Find next sibling or parent's next sibling
                        answer_elem = q.find_next(["p", "div", "li"])
                        if not answer_elem:
                            parent = q.parent
                            if parent:
                                answer_elem = parent.find_next(["p", "div", "li"])
                        answer = clean_text(answer_elem.get_text()) if answer_elem else ""
                        if answer:
                            faqs.append({"question": question, "answer": answer})
    
    # Method 3: Look for schema.org structured data
    if not faqs:
        schema_questions = soup.find_all(attrs={"itemType": "https://schema.org/Question"})
        for schema_q in schema_questions:
            question_elem = schema_q.find(attrs={"itemProp": "name"}) or schema_q.find(["h3", "h4", "h5", "h6"])
            answer_elem = schema_q.find(attrs={"itemType": "https://schema.org/Answer"})
            
            if question_elem and answer_elem:
                question = clean_text(question_elem.get_text())
                answer_text = answer_elem.find(attrs={"itemProp": "text"}) or answer_elem
                answer = clean_text(answer_text.get_text())
                
                if question and answer:
                    faqs.append({"question": question, "answers": answer})
    
    return faqs


def extract_json_data(soup: BeautifulSoup, key: str) -> Optional[any]:
    """
    Extract data from embedded JSON in script tags.
    Looks for JSON data embedded in the HTML.
    """
    # Find all script tags
    scripts = soup.find_all("script")
    
    for script in scripts:
        if not script.string:
            continue
        
        script_text = script.string
        
        # Look for JSON data with the key
        # Pattern: "key": value or "key":"value"
        patterns = [
            rf'"{key}"\s*:\s*"([^"]+)"',  # String value
            rf'"{key}"\s*:\s*(\d+\.?\d*)',  # Number value
            rf'"{key}"\s*:\s*(\[.*?\])',  # Array value
            rf'"{key}"\s*:\s*({{.*?}})',  # Object value
        ]
        
        for pattern in patterns:
            match = re.search(pattern, script_text, re.DOTALL)
            if match:
                try:
                    # Try to extract and parse JSON
                    json_str = f'{{"{key}": {match.group(1)}}}'
                    data = json.loads(json_str)
                    return data.get(key)
                except:
                    continue
    
    return None


def extract_embedded_json(soup: BeautifulSoup) -> Optional[dict]:
    """
    Extract embedded JSON data from script tags.
    Looks for __next_f.push patterns or window.__NEXT_DATA__ patterns.
    """
    scripts = soup.find_all("script")
    
    for script in scripts:
        if not script.string:
            continue
        
        script_text = script.string
        
        # Look for JSON data patterns
        # Pattern 1: __next_f.push with JSON data
        json_patterns = [
            r'__next_f\.push\(\[.*?,\s*"([^"]+)"\]\)',  # Next.js data
            r'window\.__NEXT_DATA__\s*=\s*({.+?});',  # Next.js window data
            r'"ipoData":\s*(\[.*?\])',  # IPO data array
            r'"response":\s*({.*?"ipoData".*?})',  # Response with IPO data
        ]
        
        for pattern in json_patterns:
            matches = re.finditer(pattern, script_text, re.DOTALL)
            for match in matches:
                try:
                    json_str = match.group(1)
                    # Clean up the JSON string
                    json_str = json_str.replace('\\"', '"').replace("\\'", "'")
                    data = json.loads(json_str)
                    return data
                except:
                    continue
    
    return None


def extract_date_range(soup: BeautifulSoup, label: str) -> Optional[dict]:
    """
    Extract date range (open and close dates) from a label.
    Returns dict with 'open' and 'close' keys.
    """
    value = get_value_by_label_contains(soup, label)
    if not value:
        return None
    
    # Try to parse date range like "Jan 1, 2024 - Jan 5, 2024"
    import re
    from datetime import datetime
    
    date_pattern = r"([A-Za-z]+\s+\d{1,2},\s+\d{4})"
    dates = re.findall(date_pattern, value)
    
    if len(dates) >= 2:
        try:
            open_date = datetime.strptime(dates[0], "%B %d, %Y").date()
            close_date = datetime.strptime(dates[1], "%B %d, %Y").date()
            return {"open": open_date, "close": close_date}
        except ValueError:
            pass
    
    return None
