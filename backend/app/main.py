from __future__ import annotations

from fastapi import FastAPI

from .schemas import (
    ExtractRequest,
    ExtractResponse,
    FillRequest,
    FillResponse,
    MapRequest,
    MapResponse,
    ProcessRequest,
    ProcessResponse,
)
from .services import create_extraction_response, fill_forms, map_extraction, run_full_process

app = FastAPI(
    title="Tax Codex CRA Ontario 2024 API",
    version="0.1.0",
    description="Processing pipeline for CRA 2024 Ontario identity, boxes, and other info.",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract", response_model=ExtractResponse)
def extract(request: ExtractRequest) -> ExtractResponse:
    return create_extraction_response(request)


@app.post("/map", response_model=MapResponse)
def map_endpoint(request: MapRequest) -> MapResponse:
    return map_extraction(request)


@app.post("/fill", response_model=FillResponse)
def fill_endpoint(request: FillRequest) -> FillResponse:
    return fill_forms(request)


@app.post("/process", response_model=ProcessResponse)
def process_endpoint(request: ProcessRequest) -> ProcessResponse:
    return run_full_process(request)
