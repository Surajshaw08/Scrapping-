# 📊 IPO Scraper Project Flow - Simple Explanation

## 🔄 Complete Flow (Step by Step)

### **Step 1: User Makes Request** 🌐
```
User → GET /ipo/scrape?url=https://www.chittorgarh.com/ipo/...
```

### **Step 2: FastAPI Receives Request** 🚪
**File: `app/main.py`**
- FastAPI app starts
- Routes request to `/ipo/scrape` endpoint

### **Step 3: API Endpoint** 📡
**File: `app/api/ipo.py`**
- Receives the URL from query parameter
- Calls `scrape_ipo(url)` function
- Returns the scraped data as JSON

### **Step 4: HTML Download/Save** 💾
**File: `app/scraper/fetcher.py`**
- **Option A**: Downloads fresh HTML from the website using `requests`
- **Option B**: Uses previously saved HTML from `html_cache/` folder
- Saves HTML to: `html_cache/{external_id}.html`
- Saves metadata to: `html_cache/{external_id}.json`

### **Step 5: Parse HTML** 🔍
**File: `app/scraper/parser.py`**
- Uses BeautifulSoup to convert HTML into a searchable structure
- Provides helper functions to find data:
  - `get_value_by_label_contains()` - Find values in tables
  - `extract_list()` - Extract list items
  - `extract_section_by_heading()` - Get sections by heading
  - `extract_link_by_text()` - Find links
  - And many more...

### **Step 6: Extract Data** 📋
**File: `app/scraper/chittorgarh.py`**
- Main function: `scrape_ipo()` orchestrates everything
- Internal function: `_scrape_ipo_from_soup()` does the actual extraction
- Extracts 50+ fields:
  - Basic info (name, ID, slug)
  - Issue details (size, price, dates)
  - Company info (website, sector, codes)
  - Lists (strengths, weaknesses, products, etc.)
  - URLs (DRHP, RHP, prospectus)
  - And more...

### **Step 7: Normalize Data** 🔧
**File: `app/utils/normalizers.py`**
- Converts text to proper formats:
  - `parse_float()` - "₹10 per share" → 10.0
  - `parse_int()` - "120 Shares" → 120
  - `parse_date()` - "Wed, Jan 28, 2026" → 2026-01-28

### **Step 8: Return JSON Response** 📤
- Data is validated against `app/schemas/ipo.py` (Pydantic model)
- Returns structured JSON to the user

---

## 🎯 Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    USER REQUEST                              │
│  GET /ipo/scrape?url=https://chittorgarh.com/ipo/2526/      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI App (app/main.py)                       │
│  - Receives HTTP request                                     │
│  - Routes to /ipo/scrape endpoint                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│           API Endpoint (app/api/ipo.py)                     │
│  - Extracts URL from query parameter                        │
│  - Calls scrape_ipo(url)                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│        HTML Fetcher (app/scraper/fetcher.py)                │
│  ┌──────────────────────────────────────────────┐          │
│  │ Option A: Download Fresh                     │          │
│  │  - Uses requests library                    │          │
│  │  - Downloads HTML from website              │          │
│  │  - Saves to html_cache/{id}.html            │          │
│  └──────────────────────────────────────────────┘          │
│  ┌──────────────────────────────────────────────┐          │
│  │ Option B: Use Saved HTML                     │          │
│  │  - Loads from html_cache/{id}.html          │          │
│  │  - No network request needed                │          │
│  └──────────────────────────────────────────────┘          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         HTML Parser (app/scraper/parser.py)                 │
│  - BeautifulSoup converts HTML to searchable structure      │
│  - Helper functions find specific data:                      │
│    • Tables, Lists, Sections, Links, etc.                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│      Data Extractor (app/scraper/chittorgarh.py)            │
│  - Extracts 50+ data fields:                                │
│    • Name, ID, Slug                                         │
│    • Issue Size, Price, Dates                               │
│    • Company Info, Sector                                   │
│    • Strengths, Weaknesses, Products                        │
│    • URLs, Codes, Ratings                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│      Data Normalizer (app/utils/normalizers.py)             │
│  - Converts text to proper formats:                         │
│    • "₹10" → 10.0 (float)                                   │
│    • "120 Shares" → 120 (int)                               │
│    • "Jan 28, 2026" → 2026-01-28 (date)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│         Schema Validation (app/schemas/ipo.py)              │
│  - Pydantic validates data structure                        │
│  - Ensures all fields match expected format                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    JSON RESPONSE                             │
│  Returns structured data to user                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Concepts

### **1. HTML Caching** 💾
- **Why?** Avoid re-downloading the same page
- **How?** Saves HTML to `html_cache/` folder
- **Benefit:** Faster parsing, works offline

### **2. Two-Stage Process** 🔄
- **Stage 1**: Download & Save HTML (can be done separately)
- **Stage 2**: Parse saved HTML (can be done multiple times)

### **3. Modular Design** 🧩
- **Fetcher**: Handles downloading/saving
- **Parser**: Handles HTML parsing
- **Scraper**: Orchestrates everything
- **Normalizers**: Clean and format data

---

## 📝 Example: What Happens When You Call the API

**Request:**
```
GET /ipo/scrape?url=https://www.chittorgarh.com/ipo/shadowfax-technologies-ipo/2526/
```

**What Happens:**
1. ✅ API receives request
2. ✅ Downloads HTML (or uses saved version)
3. ✅ Saves HTML to `html_cache/2526.html`
4. ✅ Parses HTML with BeautifulSoup
5. ✅ Extracts all data fields
6. ✅ Normalizes values (dates, numbers, etc.)
7. ✅ Validates against schema
8. ✅ Returns JSON response

**Response:**
```json
{
  "external_id": 2526,
  "name": "Shadowfax Technologies IPO Details",
  "issue_size_crore": 153812096,
  "listing_date": "2026-01-28",
  ...
}
```

---

## 🎯 Benefits of This Approach

1. **Efficient**: HTML saved once, parsed many times
2. **Reliable**: Works even if website is down (using saved HTML)
3. **Flexible**: Can parse from files directly
4. **Maintainable**: Each component has a single responsibility
5. **Testable**: Easy to test each part separately
