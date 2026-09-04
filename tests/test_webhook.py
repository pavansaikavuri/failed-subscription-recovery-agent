import sys
import os
import json
import hmac
import hashlib
from pathlib import Path
from datetime import datetime

# Ensure root package modules are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from starlette.testclient import TestClient

# Ensure test secret is set in environment for deterministic tests
TEST_SECRET = "test_webhook_secret_razorpay_2026"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = TEST_SECRET

from app import app, DB_PATH
from models import FailedPayment
from pipeline import classify_and_decide
from data.sample_batch import BATCH

client = TestClient(app)


def _sign(body_bytes: bytes, secret: str = TEST_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    """A valid HMAC-SHA256 signature is accepted with HTTP 200."""
    payload = {
        "event": "payment.failed",
        "event_id": f"evt_test_valid_sig_{int(datetime.now().timestamp() * 1000)}",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_valid_01",
                    "amount": 250000,
                    "method": "upi",
                    "error_reason": "insufficient_funds",
                    "attempt_count": 1,
                }
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")
    sig = _sign(body)

    resp = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "decision_made"
    assert data.get("record_id") == "pay_valid_01"
    assert "decision" in data


def test_invalid_signature_returns_401():
    """An invalid signature header returns HTTP 401 Unauthorized."""
    payload = {"event": "payment.failed", "event_id": "evt_invalid_sig_01"}
    body = json.dumps(payload).encode("utf-8")

    resp = client.post(
        "/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": "invalid_hex_digest_0000000000000000"},
    )
    assert resp.status_code == 401
    assert "Invalid webhook signature" in resp.json().get("detail", "")


def test_missing_signature_returns_401():
    """A missing X-Razorpay-Signature header returns HTTP 401 Unauthorized."""
    payload = {"event": "payment.failed", "event_id": "evt_missing_sig_01"}
    body = json.dumps(payload).encode("utf-8")

    resp = client.post("/webhooks/razorpay", content=body)
    assert resp.status_code == 401
    assert "Missing X-Razorpay-Signature header" in resp.json().get("detail", "")


def test_same_event_id_twice_yields_one_decision_and_one_duplicate_suppressed():
    """Webhook idempotency: posting the same event_id twice yields one decision and one duplicate_suppressed."""
    unique_event_id = f"evt_idempotency_test_{int(datetime.now().timestamp() * 1000)}"
    payload = {
        "event": "payment.failed",
        "event_id": unique_event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{unique_event_id}",
                    "amount": 199900,
                    "method": "upi",
                    "error_reason": "upi_pin_failure",
                    "attempt_count": 1,
                }
            }
        },
    }
    body = json.dumps(payload).encode("utf-8")
    sig = _sign(body)
    headers = {"X-Razorpay-Signature": sig}

    # Run 1: First delivery -> Decision made
    resp1 = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1.get("status") == "decision_made"

    # Run 2: Duplicate delivery -> Duplicate suppressed (idempotency ledger hit)
    resp2 = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2.get("status") == "duplicate_suppressed"
    assert data2.get("event_id") == unique_event_id


def test_webhook_decision_and_batch_decision_produce_identical_action():
    """One shared decision engine: Webhook ingestion and batch ingestion produce identical decisions."""
    # Pick a sample record from the batch
    sample_row = BATCH[0] if isinstance(BATCH[0], dict) else BATCH[0].model_dump()
    payment_obj = FailedPayment(**sample_row)

    # 1. Batch path decision
    batch_decision = classify_and_decide(payment_obj, use_llm=False)

    # 2. Webhook path delivery
    unique_event_id = f"evt_parity_test_{int(datetime.now().timestamp() * 1000)}"
    webhook_payload = {
        "event": "payment.failed",
        "event_id": unique_event_id,
        "account_id": payment_obj.merchant_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_obj.id,
                    "amount": payment_obj.amount_paise,
                    "currency": payment_obj.currency,
                    "method": payment_obj.payment_method,
                    "error_reason": payment_obj.failure_reason,
                    "attempt_count": payment_obj.attempt_count,
                    "payment_state": payment_obj.payment_state,
                    "notes": payment_obj.notes,
                }
            }
        },
    }
    body = json.dumps(webhook_payload).encode("utf-8")
    sig = _sign(body)

    resp = client.post("/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    assert resp.status_code == 200
    webhook_data = resp.json()
    webhook_action = webhook_data["decision"]["chosen_action"]

    # Must be 100% identical
    assert webhook_action == batch_decision.chosen_action, (
        f"Mismatch between ingestion paths: webhook got '{webhook_action}', batch got '{batch_decision.chosen_action}'"
    )
