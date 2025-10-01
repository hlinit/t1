"""Pydantic schemas for the CRA Ontario 2024 backend."""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class Address(BaseModel):
    street: str
    city: str
    province: str
    postal_code: str


class Contact(BaseModel):
    email: str
    phone: str


class Identity(BaseModel):
    tax_year: int = Field(..., ge=2000)
    province: str
    province_code: str
    full_name: str
    social_insurance_number: str
    date_of_birth: date
    marital_status: str
    residency_status: str
    address: Address
    contact: Contact


class Box(BaseModel):
    code: str
    label: str
    amount: float
    source: str
    line_reference: str


class ClimateActionIncentive(BaseModel):
    region: str
    adults: int
    children: int
    rural_supplement: bool


class OtherInfo(BaseModel):
    rrsp_deduction_limit: float
    rrsp_contributions: float
    union_dues: float
    childcare_expenses: float
    tuition_transfer_amount: float
    medical_expenses: float
    charitable_donations: float
    climate_action_incentive: ClimateActionIncentive
    notes: List[str]


class ExtractionData(BaseModel):
    identity: Identity
    boxes: List[Box]
    other_info: OtherInfo


class ExtractionOverrides(BaseModel):
    identity: Optional[Identity] = None
    boxes: Optional[List[Box]] = None
    other_info: Optional[OtherInfo] = None


class ExtractionMetadata(BaseModel):
    source: str
    version: str
    province: str
    warnings: List[str]
    generated_at: datetime


class ExtractRequest(BaseModel):
    document_id: Optional[str] = None
    overrides: Optional[ExtractionOverrides] = None


class ExtractResponse(BaseModel):
    data: ExtractionData
    metadata: ExtractionMetadata


class LineItem(BaseModel):
    key: str
    label: str
    amount: float
    level: Literal["federal", "provincial"]
    form: str
    reference: str


class Totals(BaseModel):
    total_income: float
    net_income: float
    taxable_income: float
    total_withholding: float
    provincial_credits: float
    federal_credits: float


class MappedData(BaseModel):
    identity: Identity
    line_items: List[LineItem]
    totals: Totals
    derived: Dict[str, float]


class MapRequest(BaseModel):
    data: ExtractionData


class MapResponse(BaseModel):
    mapped_data: MappedData


class FillField(BaseModel):
    field_id: str
    value: str | float | int


class FilledForm(BaseModel):
    name: str
    form_id: str
    year: int
    jurisdiction: str
    fields: List[FillField]


class FillResult(BaseModel):
    forms: List[FilledForm]
    summary: Dict[str, float]


class FillRequest(BaseModel):
    mapped_data: MappedData


class FillResponse(BaseModel):
    result: FillResult


class ProcessRequest(BaseModel):
    document_id: Optional[str] = None
    overrides: Optional[ExtractionOverrides] = None


class ProcessResponse(BaseModel):
    extraction: ExtractResponse
    mapping: MapResponse
    filling: FillResponse
