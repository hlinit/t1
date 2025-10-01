"""Business logic for CRA Ontario 2024 processing pipeline."""
from __future__ import annotations

from datetime import datetime, timezone

from . import data
from .schemas import (
    Box,
    ExtractRequest,
    ExtractResponse,
    ExtractionData,
    ExtractionMetadata,
    ExtractionOverrides,
    FillField,
    FillRequest,
    FillResponse,
    FillResult,
    FilledForm,
    Identity,
    LineItem,
    MapRequest,
    MapResponse,
    MappedData,
    OtherInfo,
    ProcessRequest,
    ProcessResponse,
    Totals,
)


def _apply_overrides(base: ExtractionData, overrides: ExtractionOverrides | None) -> ExtractionData:
    if not overrides:
        return base

    identity = overrides.identity or base.identity
    boxes = overrides.boxes or base.boxes
    other_info = overrides.other_info or base.other_info
    return ExtractionData(identity=identity, boxes=boxes, other_info=other_info)


def create_extraction_response(request: ExtractRequest) -> ExtractResponse:
    extraction = ExtractionData(
        identity=base_identity(),
        boxes=base_boxes(),
        other_info=base_other_info(),
    )
    extraction = _apply_overrides(extraction, request.overrides)

    metadata = ExtractionMetadata(
        source="cra-2024-ontario-static",
        version=data.CRA_ON_2024_VERSION,
        province=extraction.identity.province,
        warnings=[],
        generated_at=datetime.now(timezone.utc),
    )
    return ExtractResponse(data=extraction, metadata=metadata)


def base_identity() -> Identity:
    return Identity(**data.CRA_ON_2024_IDENTITY)


def base_boxes() -> list[Box]:
    return [Box(**entry) for entry in data.CRA_ON_2024_BOXES]


def base_other_info() -> OtherInfo:
    return OtherInfo(**data.CRA_ON_2024_OTHER_INFO)


def map_extraction(request: MapRequest) -> MapResponse:
    extraction = request.data

    income_line_codes = {"10100", "10400", "11900"}
    total_income = sum(box.amount for box in extraction.boxes if box.line_reference in income_line_codes)
    deductions = extraction.other_info.rrsp_contributions + extraction.other_info.union_dues
    net_income = max(total_income - deductions, 0.0)
    taxable_income = max(net_income - extraction.other_info.tuition_transfer_amount, 0.0)

    total_withholding = sum(
        box.amount for box in extraction.boxes if box.line_reference in {"43700", "428"}
    )

    federal_basic_personal = 15505.0
    ontario_basic_personal = 12691.0

    federal_credits = 0.15 * (federal_basic_personal + extraction.other_info.charitable_donations)
    provincial_credits = 0.0505 * (ontario_basic_personal + extraction.other_info.charitable_donations)

    line_items = [
        LineItem(
            key=f"box_{box.code}",
            label=box.label,
            amount=box.amount,
            level="provincial" if box.line_reference == "428" else "federal",
            form="ON428" if box.line_reference == "428" else "T1 General",
            reference=box.line_reference,
        )
        for box in extraction.boxes
    ]

    derived_items = [
        LineItem(
            key="line_15000",
            label="Total income",
            amount=total_income,
            level="federal",
            form="T1 General",
            reference="15000",
        ),
        LineItem(
            key="line_23600",
            label="Net income",
            amount=net_income,
            level="federal",
            form="T1 General",
            reference="23600",
        ),
        LineItem(
            key="line_26000",
            label="Taxable income",
            amount=taxable_income,
            level="federal",
            form="T1 General",
            reference="26000",
        ),
        LineItem(
            key="line_43700",
            label="Total income tax deducted",
            amount=sum(box.amount for box in extraction.boxes if box.line_reference == "43700"),
            level="federal",
            form="T1 General",
            reference="43700",
        ),
        LineItem(
            key="on428_line_1",
            label="Ontario tax deducted",
            amount=sum(box.amount for box in extraction.boxes if box.line_reference == "428"),
            level="provincial",
            form="ON428",
            reference="428",
        ),
    ]

    line_items.extend(derived_items)

    totals = Totals(
        total_income=total_income,
        net_income=net_income,
        taxable_income=taxable_income,
        total_withholding=total_withholding,
        provincial_credits=provincial_credits,
        federal_credits=federal_credits,
    )

    derived = {
        "federal_basic_personal_amount": federal_basic_personal,
        "ontario_basic_personal_amount": ontario_basic_personal,
        "total_deductions": deductions,
        "climate_action_incentive_estimate": _calculate_cai(
            extraction.other_info.climate_action_incentive.adults,
            extraction.other_info.climate_action_incentive.children,
            extraction.other_info.climate_action_incentive.rural_supplement,
        ),
    }

    mapped_data = MappedData(identity=extraction.identity, line_items=line_items, totals=totals, derived=derived)
    return MapResponse(mapped_data=mapped_data)


def fill_forms(request: FillRequest) -> FillResponse:
    mapped = request.mapped_data

    federal_tax_payable = max(mapped.totals.taxable_income * 0.15 - mapped.totals.federal_credits, 0.0)
    provincial_tax_payable = max(mapped.totals.taxable_income * 0.0505 - mapped.totals.provincial_credits, 0.0)
    balance = mapped.totals.total_withholding - (federal_tax_payable + provincial_tax_payable)

    t1_fields = [
        FillField(field_id="identity.full_name", value=mapped.identity.full_name),
        FillField(field_id="identity.sin", value=mapped.identity.social_insurance_number),
        FillField(
            field_id="identity.address",
            value=f"{mapped.identity.address.street}, {mapped.identity.address.city} {mapped.identity.address.postal_code}",
        ),
        FillField(field_id="line15000", value=round(mapped.totals.total_income, 2)),
        FillField(field_id="line23600", value=round(mapped.totals.net_income, 2)),
        FillField(field_id="line26000", value=round(mapped.totals.taxable_income, 2)),
        FillField(field_id="line43700", value=round(mapped.totals.total_withholding, 2)),
    ]

    on428_fields = [
        FillField(field_id="identity.full_name", value=mapped.identity.full_name),
        FillField(field_id="line1", value=round(mapped.totals.total_withholding, 2)),
        FillField(field_id="line19", value=round(mapped.totals.provincial_credits, 2)),
    ]

    forms = [
        FilledForm(
            name="T1 General",
            form_id="t1-general",
            year=mapped.identity.tax_year,
            jurisdiction="Federal",
            fields=t1_fields,
        ),
        FilledForm(
            name="ON428",
            form_id="on428",
            year=mapped.identity.tax_year,
            jurisdiction="Ontario",
            fields=on428_fields,
        ),
    ]

    summary = {
        "federal_tax_payable": round(federal_tax_payable, 2),
        "provincial_tax_payable": round(provincial_tax_payable, 2),
        "balance_due_or_refund": round(balance, 2),
    }

    result = FillResult(forms=forms, summary=summary)
    return FillResponse(result=result)


def run_full_process(request: ProcessRequest) -> ProcessResponse:
    extraction_response = create_extraction_response(
        ExtractRequest(document_id=request.document_id, overrides=request.overrides)
    )
    mapping_response = map_extraction(MapRequest(data=extraction_response.data))
    filling_response = fill_forms(FillRequest(mapped_data=mapping_response.mapped_data))

    return ProcessResponse(
        extraction=extraction_response,
        mapping=mapping_response,
        filling=filling_response,
    )


def _calculate_cai(adults: int, children: int, rural: bool) -> float:
    base_amount = 488.0  # 2024 Ontario first adult estimate
    second_adult = 244.0 if adults > 1 else 0.0
    child_amount = 122.0 * children
    rural_bonus = 0.1 * (base_amount + second_adult + child_amount) if rural else 0.0
    return round(base_amount + second_adult + child_amount + rural_bonus, 2)
