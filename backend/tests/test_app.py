import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_extract_endpoint_returns_default_dataset():
    response = client.post("/extract", json={})
    assert response.status_code == 200
    payload = response.json()

    assert payload["data"]["identity"]["province"] == "Ontario"
    assert payload["metadata"]["source"] == "cra-2024-ontario-static"
    assert payload["data"]["other_info"]["climate_action_incentive"]["region"] == "Ontario"


def test_map_endpoint_generates_totals():
    extraction = client.post("/extract", json={}).json()["data"]
    response = client.post("/map", json={"data": extraction})
    assert response.status_code == 200
    mapped = response.json()["mapped_data"]

    assert mapped["totals"]["total_income"] > 0
    assert any(item["key"] == "line_15000" for item in mapped["line_items"])


def test_process_endpoint_runs_full_pipeline():
    response = client.post("/process", json={})
    assert response.status_code == 200
    body = response.json()

    assert "extraction" in body
    assert "mapping" in body
    assert "filling" in body
    assert body["filling"]["result"]["summary"]["balance_due_or_refund"] is not None
