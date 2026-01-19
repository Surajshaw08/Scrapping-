from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

# --- Sub Models ---

class Objective(BaseModel):
    sno: int
    description: str
    amount_crore: float

class Financial(BaseModel):
    period_label: str
    period_end_date: date
    assets: float
    total_income: float
    pat: float
    ebitda: float
    net_worth: float
    reserves: float
    borrowings: float

class Peer(BaseModel):
    company: str
    eps_basic: float
    eps_diluted: float
    nav: float
    pe: float
    ronw: float

class CompanyContact(BaseModel):
    name: str
    address: str
    phone: str
    email: str
    website: str

class Registrar(BaseModel):
    name: str
    phone_numbers: List[str]
    email: str
    website: str

class Reservation(BaseModel):
    qib: float
    anchor: float
    ex_anchor: float
    nii: float
    bnii: float
    snii: float
    retail: float
    employee: float
    shareholder: float
    other: float
    total: float

class FAQ(BaseModel):
    question: str
    answers: str

class RHPInsight(BaseModel):
    tittle: str
    description: str
    impact: int

# --- MAIN IPO MODEL ---

class IPO(BaseModel):
    external_id: int
    slug: str
    name: str
    category: str
    exchange: str

    issue_size_crore: Optional[float] = None
    fresh_issue_crore: Optional[float] = None
    ofs_issue_crore: Optional[float] = None
    market_maker_reserved_crore: Optional[float] = None

    face_value: Optional[float] = None
    issue_type: Optional[str] = None
    issue_price_low: Optional[float] = None
    issue_price_high: Optional[float] = None
    lot_size: Optional[int] = None
    single_lot_price: Optional[float] = None
    small_hni_lot: Optional[int] = None
    big_hni_lot: Optional[int] = None

    issue_open_date: Optional[date] = None
    issue_close_date: Optional[date] = None
    allotment_date: Optional[date] = None
    refund_date: Optional[date] = None
    listing_date: Optional[date] = None
    boa_date: Optional[date] = None
    cos_date: Optional[date] = None

    promoter_holding_pre: Optional[float] = None
    promoter_holding_post: Optional[float] = None

    website: Optional[str] = None
    sector: Optional[str] = None

    about_company: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    products: List[str] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    promoters: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    threats: List[str] = Field(default_factory=list)

    drhp_url: Optional[str] = None
    rhp_url: Optional[str] = None
    final_prospectus_url: Optional[str] = None
    anchor_list_url: Optional[str] = None
    logo_url: Optional[str] = None

    bse_code: Optional[str] = None
    nse_code: Optional[str] = None
    isTentative: bool = True
    rating: Optional[float] = None
    listing_price: Optional[float] = None

    objectives: List[Objective] = Field(default_factory=list)
    financials: List[Financial] = Field(default_factory=list)
    peers: List[Peer] = Field(default_factory=list)
    company_contacts: List[CompanyContact] = Field(default_factory=list)
    registrar: Optional[Registrar] = None
    lead_managers: List[str] = Field(default_factory=list)
    reservations: List[Reservation] = Field(default_factory=list)
    faqs: List[FAQ] = Field(default_factory=list)
    rhp_insights: List[RHPInsight] = Field(default_factory=list)

    class Config:
        from_attributes = True
