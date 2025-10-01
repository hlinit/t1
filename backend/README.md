# Backend (FastAPI)
## Setup
- Create .env from .env.example and fill values.

## Run
uvicorn main:app --reload --port 8000

## Debug storage
GET http://localhost:8000/api/storage/template-info

## Endpoints
- POST /api/extract  (upload T4 -> JSON with identity, boxes, otherInfo)
- POST /api/map      (post normalized JSON -> byLine/byField; uses T1 field names from blob)
- POST /api/fill     (post byField -> PDF stream or blob URL if saving)
- POST /api/process  (upload T4 -> filled PDF)

## Notes
- Hard-coded to CRA 2024 / Ontario in prompts.
- No year/province in payloads.
- Field names are read from the T1 template in Azure Blob.
