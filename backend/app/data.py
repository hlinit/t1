"""Static data for CRA 2024 Ontario returns."""
from __future__ import annotations

from datetime import date

CRA_ON_2024_IDENTITY = {
    "tax_year": 2024,
    "province": "Ontario",
    "province_code": "ON",
    "full_name": "Alexandra Doe",
    "social_insurance_number": "123 456 789",
    "date_of_birth": date(1988, 2, 14),
    "marital_status": "Single",
    "residency_status": "Resident",
    "address": {
        "street": "123 Bay Street",
        "city": "Toronto",
        "province": "ON",
        "postal_code": "M5J 2N8",
    },
    "contact": {
        "email": "alexandra.doe@example.com",
        "phone": "416-555-0199",
    },
}

CRA_ON_2024_BOXES = [
    {
        "code": "101",
        "label": "Employment income (box 14, T4)",
        "amount": 78500.00,
        "source": "T4",
        "line_reference": "10100",
    },
    {
        "code": "104",
        "label": "Other employment income",
        "amount": 1200.00,
        "source": "T4",
        "line_reference": "10400",
    },
    {
        "code": "105",
        "label": "Employment insurance benefits",
        "amount": 0.0,
        "source": "T4E",
        "line_reference": "11900",
    },
    {
        "code": "117",
        "label": "Registered pension plan (RPP) contributions",
        "amount": 2500.00,
        "source": "T4",
        "line_reference": "20700",
    },
    {
        "code": "312",
        "label": "CPP contributions",
        "amount": 3567.50,
        "source": "T4",
        "line_reference": "30800",
    },
    {
        "code": "400",
        "label": "Income tax deducted",
        "amount": 15670.00,
        "source": "T4",
        "line_reference": "43700",
    },
    {
        "code": "Ontario-428",
        "label": "Ontario tax deducted",
        "amount": 3640.00,
        "source": "T4",
        "line_reference": "428",
    },
]

CRA_ON_2024_OTHER_INFO = {
    "rrsp_deduction_limit": 18600.00,
    "rrsp_contributions": 8000.00,
    "union_dues": 450.00,
    "childcare_expenses": 0.0,
    "tuition_transfer_amount": 0.0,
    "medical_expenses": 1200.00,
    "charitable_donations": 600.00,
    "climate_action_incentive": {
        "region": "Ontario",
        "adults": 1,
        "children": 0,
        "rural_supplement": False,
    },
    "notes": [
        "Taxpayer eligible for basic Ontario energy and property tax credit.",
        "No dependants claimed for 2024.",
    ],
}

CRA_ON_2024_VERSION = "2024.1.0"
