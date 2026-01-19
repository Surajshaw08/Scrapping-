from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class CouponSeries(BaseModel):
    series_name: str
    frequency_of_interest_payment: str
    nature: str
    tenor: str
    coupon_percent_pa: float
    effective_yield_percent_pa: float
    amount_on_maturity: float


class Rating(BaseModel):
    rating_agency: str
    ncd_rating: str
    outlook: str
    safety_degree: str
    risk_degree: str


class FinancialPeriod(BaseModel):
    period_end: str
    assets: float
    total_income: float
    profit_after_tax: float


class CompanyFinancials(BaseModel):
    unit: str
    periods: List[FinancialPeriod] = Field(default_factory=list)


class AllocationCategory(BaseModel):
    category: str
    allocated_percentage: float
    shares_reserved: float


class NCDAllocation(BaseModel):
    total_shares: float
    categories: List[AllocationCategory] = Field(default_factory=list)


class CompanyContact(BaseModel):
    company_name: str
    address_line_1: str
    city: str
    state: str
    pincode: str
    phone_numbers: List[str] = Field(default_factory=list)
    email: str
    website: str


class Registrar(BaseModel):
    name: str
    phone_numbers: List[str] = Field(default_factory=list)
    email: str
    website: str


class Document(BaseModel):
    title: str
    url: str


class FAQ(BaseModel):
    question: str
    answer: str


class NCD(BaseModel):
    slug: str
    issuer: str
    issue_name: str
    logo_url: Optional[str] = None
    description: str
    open_date: Optional[date] = None
    close_date: Optional[date] = None
    issue_size_overall: Optional[float] = None
    coupon_rate_min: Optional[float] = None
    coupon_rate_max: Optional[float] = None
    security_name: Optional[str] = None
    security_type: Optional[str] = None
    issue_size_base: Optional[float] = None
    issue_size_oversubscription: Optional[float] = None
    overall_issue_size: Optional[float] = None
    issue_price_per_ncd: Optional[float] = None
    face_value_per_ncd: Optional[float] = None
    minimum_lot_size_ncd: Optional[float] = None
    market_lot_ncd: Optional[float] = None
    exchanges: List[str] = Field(default_factory=list)
    basis_of_allotment: Optional[str] = None
    debenture_trustee: Optional[str] = None
    promoters: List[str] = Field(default_factory=list)
    coupon_series: List[CouponSeries] = Field(default_factory=list)
    ratings: List[Rating] = Field(default_factory=list)
    company_financials: Optional[CompanyFinancials] = None
    ncd_allocation: Optional[NCDAllocation] = None
    objects_of_issue: List[str] = Field(default_factory=list)
    company_contact: Optional[CompanyContact] = None
    registrar: Optional[Registrar] = None
    lead_managers: List[str] = Field(default_factory=list)
    documents: List[Document] = Field(default_factory=list)
    faq: List[FAQ] = Field(default_factory=list)
    news: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True
