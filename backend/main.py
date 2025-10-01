from __future__ import annotations

import io
import json
import logging
import os
import re
import uuid
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union

import httpx
from pypdf import PdfReader
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from .models import ExtractedPayload, FillInput, MapResult, NormalizedIdentity, NormalizedPayload
from .routes.storage_debug import router as storage_router
from .utils.storage import StorageError, get_t1_template_bytes, upload_completed_t1
from .utils.t1_fields import get_t1_field_names
from .utils.fill_t1 import fill_t1_pdf

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


_ENV_LOADED = False

def _load_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_dir = Path(__file__).resolve().parent
    candidates = [env_dir / ".env", env_dir.parent / ".env"]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            os.environ.setdefault(key, value)
        break

    _ENV_LOADED = True


class Settings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    azure_openai_endpoint: str = Field(alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_key: str = Field(
        alias="AZURE_OPENAI_KEY",
        validation_alias=AliasChoices("AZURE_OPENAI_KEY", "AZURE_OPENAI_API_KEY"),
    )
    azure_openai_api_version: str = Field(default="2024-02-15-preview", alias="AZURE_OPENAI_API_VERSION")
    azure_openai_extensions_api_version: Optional[str] = Field(default=None, alias="AZURE_OPENAI_EXTENSIONS_API_VERSION")
    azure_openai_extract_deployment: str = Field(
        alias="AZURE_OPENAI_EXTRACT_DEPLOYMENT",
        validation_alias=AliasChoices("AZURE_OPENAI_EXTRACT_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT"),
    )
    azure_openai_map_deployment: str = Field(
        alias="AZURE_OPENAI_MAP_DEPLOYMENT",
        validation_alias=AliasChoices("AZURE_OPENAI_MAP_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT"),
    )

    azure_search_endpoint: Optional[str] = Field(default=None, alias="AZURE_SEARCH_ENDPOINT")
    azure_search_index: Optional[str] = Field(default=None, alias="AZURE_SEARCH_INDEX")
    azure_search_key: Optional[str] = Field(default=None, alias="AZURE_SEARCH_KEY")
    azure_search_semantic_config: Optional[str] = Field(default=None, alias="AZURE_SEARCH_SEMANTIC_CONFIG")
    azure_search_content_fields: str = Field(default="content", alias="AZURE_SEARCH_CONTENT_FIELDS")
    azure_search_title_field: Optional[str] = Field(default="title", alias="AZURE_SEARCH_TITLE_FIELD")
    azure_search_url_field: Optional[str] = Field(default="source_url", alias="AZURE_SEARCH_URL_FIELD")
    azure_search_role_information: Optional[str] = Field(default=None, alias="AZURE_SEARCH_ROLE_INFORMATION")
    azure_search_top_n: int = Field(default=5, alias="AZURE_SEARCH_TOP_N")
    azure_search_strictness: int = Field(default=3, alias="AZURE_SEARCH_STRICTNESS")
    azure_search_filter: Optional[str] = Field(default=None, alias="AZURE_SEARCH_FILTER")

    cors_allow_origins: str = Field(default="*", alias="CORS_ALLOW_ORIGINS")

    def parsed_data_sources(self) -> Optional[List[Dict[str, Any]]]:
        if not (self.azure_search_endpoint and self.azure_search_index and self.azure_search_key):
            return None

        content_fields = [field.strip() for field in self.azure_search_content_fields.split(',') if field.strip()]
        if not content_fields:
            content_fields = ["content"]

        parameters: Dict[str, Any] = {
            "endpoint": self.azure_search_endpoint,
            "index_name": self.azure_search_index,
            "authentication": {"type": "api_key", "key": self.azure_search_key},
            "in_scope": True,
            "top_n_documents": max(1, self.azure_search_top_n),
        }

        if self.azure_search_semantic_config:
            parameters["semantic_configuration"] = self.azure_search_semantic_config
            parameters["query_type"] = "semantic"
            parameters["strictness"] = max(1, self.azure_search_strictness)
        else:
            parameters["query_type"] = "simple"

        if self.azure_search_filter:
            parameters["filter"] = self.azure_search_filter

        return [{"type": "azure_search", "parameters": parameters}]

    def allow_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()] or ["*"]

@lru_cache
def get_settings() -> Settings:
    _load_env_file()
    try:
        return Settings(**os.environ)
    except ValidationError as exc:  # pragma: no cover - configuration stage
        raise RuntimeError(f"Backend configuration error: {exc}") from exc

@lru_cache
def _load_t1_template() -> bytes:
    return get_t1_template_bytes()


def _should_save_output() -> bool:
    return os.getenv("SAVE_OUTPUT_TO_BLOB", "false").lower() == "true"

def _maybe_upload_pdf(pdf_bytes: bytes) -> Optional[str]:
    if not _should_save_output():
        return None
    blob_name = f"t1-{uuid.uuid4().hex}.pdf"
    try:
        url = upload_completed_t1(pdf_bytes, blob_name)
    except StorageError as exc:
        logger.error("Failed to upload filled PDF: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Failed to upload filled PDF"}) from exc
    return url or None

def _pdf_response(pdf_bytes: bytes):
    url = _maybe_upload_pdf(pdf_bytes)
    if url:
        return JSONResponse({"url": url})
    stream = io.BytesIO(pdf_bytes)
    headers = {"Content-Disposition": 'attachment; filename="t1-filled.pdf"'}
    return StreamingResponse(stream, media_type="application/pdf", headers=headers)

async def _call_azure_openai(
    *,
    settings: Settings,
    deployment: str,
    messages: List[Dict[str, str]],
    data_sources: Optional[List[Dict[str, Any]]] = None,
) -> str:
    base_path = "chat/completions"
    api_version = settings.azure_openai_extensions_api_version or settings.azure_openai_api_version
    url = (
        f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/{deployment}/{base_path}"
        f"?api-version={api_version}"
    )
    payload: Dict[str, Any] = {
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    logger.info("Azure OpenAI URL: %s (api=%s, extensions=%s)", url, api_version if 'api_version' in locals() else settings.azure_openai_api_version, bool(data_sources))
    if data_sources:
        payload["data_sources"] = data_sources
        logger.info("Azure dataSources payload: %s", json.dumps(data_sources, ensure_ascii=False))
    else:
        logger.debug("Calling Azure OpenAI without dataSources")

    headers = {
        "Content-Type": "application/json",
        "api-key": settings.azure_openai_key,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code != 200:
        logger.error("Azure OpenAI request failed: %s - %s", response.status_code, response.text)
        raise HTTPException(status_code=502, detail={"error": "Azure OpenAI request failed"})

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:  # pragma: no cover - unexpected
        logger.exception("Azure OpenAI response missing content")
        raise HTTPException(status_code=502, detail={"error": "Azure OpenAI response malformed"}) from exc

    if isinstance(content, list):
        fragments = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "".join(fragments)
    return str(content)

async def _call_model_with_retry(
    *,
    settings: Settings,
    deployment: str,
    base_messages: List[Dict[str, str]],
    data_sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    messages = list(base_messages)
    raw = await _call_azure_openai(settings=settings, deployment=deployment, messages=messages, data_sources=data_sources)
    try:
        return _coerce_json_dict(raw)
    except (ValueError, json.JSONDecodeError):
        logger.warning("Model returned invalid JSON; retrying once. Raw response: %s", raw)
        retry_messages = messages + [{"role": "user", "content": "Return strict JSON only."}]
        raw_retry = await _call_azure_openai(
            settings=settings,
            deployment=deployment,
            messages=retry_messages,
            data_sources=data_sources,
        )
        try:
            return _coerce_json_dict(raw_retry)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("Model returned invalid JSON after retry. Raw response: %s", raw_retry)
            raise HTTPException(status_code=422, detail={"error": "Model response was not valid JSON"}) from exc

FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _coerce_json_dict(raw: str) -> Dict[str, Any]:
    if raw is None:
        raise ValueError('Empty response')
    text = str(raw).strip()
    if not text:
        raise ValueError('Empty response')

    match = FENCED_JSON_RE.search(text)
    if match:
        text = match.group(1).strip()
    elif text.startswith('```'):
        text = text.strip('`').strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed

    raise ValueError('Response did not contain valid JSON object')


STRING_BOXES = {"10", "12", "54"}
NUMERIC_STRIP_RE = re.compile(r"[^0-9.+-]")
FIELD_KEY_RE = re.compile(r"(Slip\d+(?:Box|Amount)[A-Za-z0-9]+)")
BOX_SUFFIX_RE = re.compile(r"Box([0-9A-Za-z]+)")
AMOUNT_SUFFIX_RE = re.compile(r"Amount([0-9A-Za-z]+)")


def _extract_suffix(pattern: re.Pattern[str], value: str) -> Optional[str]:
    match = pattern.search(value)
    if not match:
        return None
    return match.group(1)


def _simplify_pdf_value(raw: Any) -> Optional[Any]:
    if raw is None:
        return None
    if isinstance(raw, (str, int, float)):
        return raw
    if hasattr(raw, "get_object"):
        try:
            return _simplify_pdf_value(raw.get_object())
        except Exception:
            return None
    text_value = str(raw).strip()
    if not text_value:
        return None
    if text_value.startswith("/") and len(text_value) > 1:
        return text_value[1:]
    return text_value


def _coerce_nonempty_string(value: Any) -> Optional[str]:
    simplified = _simplify_pdf_value(value)
    if simplified is None:
        return None
    if isinstance(simplified, (int, float)):
        simplified = f"{simplified}"
    if isinstance(simplified, str):
        stripped = simplified.strip()
        return stripped or None
    text_value = str(simplified).strip()
    return text_value or None


def _normalize_numeric_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text_value = str(value).strip()
    if not text_value:
        return None
    cleaned = NUMERIC_STRIP_RE.sub("", text_value.replace(",", ""))
    if not cleaned:
        return None
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def _normalize_box_value(box_number: str, value: Any) -> Optional[Union[float, str]]:
    if box_number in STRING_BOXES:
        text = _coerce_nonempty_string(value)
        if text is None:
            return None
        if box_number == "12":
            return text.replace(" ", "")
        return text
    return _normalize_numeric_value(value)


def _read_form_values(pdf_bytes: bytes) -> Dict[str, Any]:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        logger.error("Failed to open PDF: %s", exc)
        raise HTTPException(status_code=400, detail={"error": "Unable to read PDF form fields"}) from exc

    collected: Dict[str, Any] = {}
    try:
        text_fields = reader.get_form_text_fields() or {}
    except Exception as exc:
        logger.debug("get_form_text_fields failed: %s", exc)
        text_fields = {}
    for name, value in text_fields.items():
        simplified = _simplify_pdf_value(value)
        if simplified is not None:
            collected[name] = simplified

    try:
        fields = reader.get_fields() or {}
    except Exception as exc:
        logger.error("Failed to load AcroForm fields: %s", exc)
        raise HTTPException(status_code=400, detail={"error": "Unable to read PDF form fields"}) from exc

    for name, field in fields.items():
        if name in collected:
            continue
        current = None
        for key in ("value", "/V"):
            try:
                current = field.get(key)
            except Exception:
                current = None
            if current is not None:
                break
        if current is None and hasattr(field, "value"):
            current = getattr(field, "value")
        simplified = _simplify_pdf_value(current)
        if simplified is not None:
            collected[name] = simplified
    return collected


def _list_form_field_names(pdf_bytes: bytes) -> List[str]:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        fields = reader.get_fields() or {}
    except Exception as exc:
        logger.error("Failed to read PDF form fields: %s", exc)
        raise HTTPException(status_code=400, detail={"error": "Unable to read PDF form fields"}) from exc
    return sorted(str(name) for name in fields.keys())


async def _extract_payload(pdf_bytes: bytes) -> ExtractedPayload:
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail={"error": "Uploaded file is empty"})

    raw_values = _read_form_values(pdf_bytes)
    boxes: Dict[str, Union[float, str]] = {}
    other_codes: Dict[str, str] = {}
    other_amounts: Dict[str, float] = {}

    for field_name, raw_value in raw_values.items():
        field_key_match = FIELD_KEY_RE.search(field_name)
        if not field_key_match:
            continue
        field_key = field_key_match.group(1)

        if "OtherInformation" in field_name:
            if "Amount" in field_key:
                slot = _extract_suffix(AMOUNT_SUFFIX_RE, field_key)
                if not slot:
                    continue
                amount_value = _normalize_numeric_value(raw_value)
                if amount_value is not None:
                    other_amounts[slot.upper()] = amount_value
            else:
                slot = _extract_suffix(BOX_SUFFIX_RE, field_key)
                if not slot:
                    continue
                code_value = _coerce_nonempty_string(raw_value)
                if code_value:
                    other_codes[slot.upper()] = code_value
            continue

        if "Amount" in field_key:
            continue

        box_number = _extract_suffix(BOX_SUFFIX_RE, field_key)
        if not box_number:
            continue
        box_number = box_number.upper()
        value = _normalize_box_value(box_number, raw_value)
        if value is not None:
            boxes[box_number] = value


    other_info: Dict[str, float] = {}
    for slot, code in other_codes.items():
        amount = other_amounts.get(slot)
        if amount is None:
            continue
        other_info[code] = amount

    payload = ExtractedPayload(year="2024", boxes=boxes, otherInfo=other_info)
    return payload


def _to_normalized_payload(extracted: ExtractedPayload) -> NormalizedPayload:
    return NormalizedPayload(
        identity=NormalizedIdentity(),
        boxes=dict(extracted.boxes),
        otherInfo=dict(extracted.otherInfo),
    )


async def _map_payload(payload: NormalizedPayload, settings: Settings, field_names: List[str]) -> MapResult:
    sample_field = field_names[0] if field_names else "T1_FIELD_NAME"
    example_output = {
        "byLine": {"Line 10100": 12345.67},
        "byField": {sample_field: "Example value"},
    }
    system_prompt = """You are a Canadian tax assistant.
Ground all answers in the CRA T1 2024 General Guide (5000-G-24E) loaded into Azure AI Search.
Tasks:
1. Map T4 \"boxes\" and \"otherInfo\" to CRA T1 line numbers using rules in the Guide.
2. Populate T1 personal information fields from \"identity\" (firstName, lastName, initial, sin, address, employer, payrollAccount).
3. Output STRICT JSON only:
{
  \"byLine\": { \"Line 10100\": number, ... },
  \"byField\": { \"<T1_PDF_field_name>\": number|string, ... }
}
Rules:
- Use only CRA lines described in the retrieved Guide content.
- Do not invent line numbers or field names.
- If no relevant content is retrieved, omit the mapping.
- Return JSON only, no prose or Markdown."""
    prompt_body = {
        "normalizedInput": payload.model_dump(exclude_none=True),
        "t1FieldNames": field_names,
        "exampleOutput": example_output,
    }
    user_prompt = (
        "Extract the required mapping using the supplied data. Return JSON only.\n"
        + json.dumps(prompt_body)
    )

    base_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    data_sources = settings.parsed_data_sources()
    logger.info("Azure map request payload: %s", json.dumps(base_messages, ensure_ascii=False))
    payload_map = await _call_model_with_retry(
        settings=settings,
        deployment=settings.azure_openai_map_deployment,
        base_messages=base_messages,
        data_sources=data_sources,
    )
    logger.info("Azure map response payload: %s", json.dumps(payload_map, ensure_ascii=False))

    try:
        result = MapResult.model_validate(payload_map)
    except ValidationError as exc:
        logger.error("Mapping output validation failed: %s", exc)
        raise HTTPException(status_code=422, detail={"error": "Mapping output invalid"}) from exc

    filtered_fields = {k: result.byField[k] for k in result.byField if k in field_names}
    return MapResult(byLine=result.byLine, byField=filtered_fields)

app = FastAPI(title="Tax Codex CRA Ontario 2024 API", version="0.2.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(storage_router, prefix="/api/storage", tags=["storage"])

@app.post("/api/extract")
async def extract_endpoint(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail={"error": "File name is required"})
    if not file.content_type or "pdf" not in file.content_type.lower():
        raise HTTPException(status_code=400, detail={"error": "Only PDF files are supported"})
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail={"error": "Uploaded file is empty"})

    extracted = await _extract_payload(pdf_bytes)
    return JSONResponse(extracted.model_dump(exclude_none=True))

@app.get("/api/list-fields")
async def list_fields(file: str) -> JSONResponse:
    if not file:
        raise HTTPException(status_code=400, detail={"error": "Query parameter 'file' is required"})
    file_path = Path(file)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail={"error": "File not found"})
    try:
        pdf_bytes = file_path.read_bytes()
    except Exception as exc:
        logger.error("Failed to read PDF for list-fields: %s", exc)
        raise HTTPException(status_code=400, detail={"error": "Unable to read provided file"}) from exc
    fields = _list_form_field_names(pdf_bytes)
    return JSONResponse({"fields": fields})


@app.post("/api/map")
async def map_endpoint(payload: ExtractedPayload) -> JSONResponse:
    try:
        template_bytes = get_t1_template_bytes()
    except StorageError as exc:
        logger.error("Failed to load T1 template from storage: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Unable to load T1 template"}) from exc
    try:
        field_names = get_t1_field_names(template_bytes)
    except Exception as exc:
        logger.error("Failed to extract T1 field names: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Unable to read T1 field names"}) from exc

    normalized_input = _to_normalized_payload(payload)
    mapped = await _map_payload(normalized_input, settings, field_names)
    return JSONResponse(mapped.model_dump())

@app.post("/api/fill")
async def fill_endpoint(body: FillInput):
    try:
        template_bytes = _load_t1_template()
    except StorageError as exc:
        logger.error("Failed to load T1 template from storage: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Unable to load T1 template"}) from exc
    except Exception as exc:
        logger.error("Failed to read T1 template: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Unable to read T1 template"}) from exc

    try:
        pdf_bytes = fill_t1_pdf(template_bytes, body.byField)
    except Exception as exc:
        logger.error("Failed to fill T1 PDF: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Failed to fill T1 PDF"}) from exc

    return _pdf_response(pdf_bytes)

@app.post("/api/process")
async def process_endpoint(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail={"error": "File name is required"})
    if not file.content_type or "pdf" not in file.content_type.lower():
        raise HTTPException(status_code=400, detail={"error": "Only PDF files are supported"})
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail={"error": "Uploaded file is empty"})

    extracted = await _extract_payload(pdf_bytes)
    try:
        template_bytes = get_t1_template_bytes()
    except StorageError as exc:
        logger.error("Failed to load T1 template from storage: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Unable to load T1 template"}) from exc
    try:
        field_names = get_t1_field_names(template_bytes)
    except Exception as exc:
        logger.error("Failed to extract T1 field names: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Unable to read T1 field names"}) from exc

    normalized_input = _to_normalized_payload(extracted)
    mapped = await _map_payload(normalized_input, settings, field_names)
    try:
        filled_pdf = fill_t1_pdf(template_bytes, mapped.byField)
    except Exception as exc:
        logger.error("Failed to fill T1 PDF: %s", exc)
        raise HTTPException(status_code=500, detail={"error": "Failed to fill T1 PDF"}) from exc

    return _pdf_response(filled_pdf)
@app.get("/debug/storage")
def storage_debug() -> Dict[str, Any]:
    details = {
        "has_connection_str": bool(os.getenv("AZURE_STORAGE_CONNECTION_STRING")),
        "template_container": os.getenv("AZURE_STORAGE_CONTAINER"),
        "template_blob": os.getenv("AZURE_STORAGE_BLOB"),
        "output_container": os.getenv("AZURE_OUTPUT_CONTAINER"),
        "save_output_to_blob": os.getenv("SAVE_OUTPUT_TO_BLOB", "false"),
    }
    try:
        template_bytes = _load_t1_template()
        details["template_bytes"] = len(template_bytes)
    except StorageError as exc:
        details["error"] = str(exc)
    return details


@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}








