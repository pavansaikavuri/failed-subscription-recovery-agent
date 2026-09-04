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


def test_multi_attempt_dunning_continuity_exhausts_upi_cap():
    """
    Webhook state continuity: 3 successive payment failures for the same subscription_id
    progress through retry_now -> retry_now -> stop_and_writeoff (Guard 2: retry_cap).
    """
    sub_id = f"sub_dunning_test_{int(datetime.now().timestamp() * 1000)}"

    # Attempt 1
    p1 = {
        "event": "payment.failed",
        "event_id": f"evt_{sub_id}_1",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{sub_id}_1",
                    "subscription_id": sub_id,
                    "amount": 19900,
                    "method": "upi",
                    "error_reason": "insufficient_funds",
                }
            }
        },
    }
    b1 = json.dumps(p1).encode("utf-8")
    r1 = client.post("/webhooks/razorpay", content=b1, headers={"X-Razorpay-Signature": _sign(b1)})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["attempt_number"] == 1
    assert d1["decision"]["chosen_action"] == "retry_now"

    # Attempt 2
    p2 = {
        "event": "payment.failed",
        "event_id": f"evt_{sub_id}_2",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{sub_id}_2",
                    "subscription_id": sub_id,
                    "amount": 19900,
                    "method": "upi",
                    "error_reason": "insufficient_funds",
                }
            }
        },
    }
    b2 = json.dumps(p2).encode("utf-8")
    r2 = client.post("/webhooks/razorpay", content=b2, headers={"X-Razorpay-Signature": _sign(b2)})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["attempt_number"] == 2
    assert d2["decision"]["chosen_action"] == "retry_now"

    # Attempt 3 (UPI Cap is 3 -> attempt_count >= 3 triggers Guard 2)
    p3 = {
        "event": "payment.failed",
        "event_id": f"evt_{sub_id}_3",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{sub_id}_3",
                    "subscription_id": sub_id,
                    "amount": 19900,
                    "method": "upi",
                    "error_reason": "insufficient_funds",
                }
            }
        },
    }
    b3 = json.dumps(p3).encode("utf-8")
    r3 = client.post("/webhooks/razorpay", content=b3, headers={"X-Razorpay-Signature": _sign(b3)})
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["attempt_number"] == 3
    assert d3["decision"]["chosen_action"] == "stop_and_writeoff"
    assert d3["decision"]["guard_triggered"] == "retry_cap"


def test_subscription_endpoint_returns_full_history():
    """GET /subscriptions/{subscription_id} returns all prior events and decisions in chronological order."""
    sub_id = f"sub_hist_test_{int(datetime.now().timestamp() * 1000)}"

    for att in (1, 2):
        payload = {
            "event": "payment.failed",
            "event_id": f"evt_{sub_id}_{att}",
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_{sub_id}_{att}",
                        "subscription_id": sub_id,
                        "amount": 19900,
                        "method": "upi",
                        "error_reason": "insufficient_funds",
                    }
                }
            },
        }
        b = json.dumps(payload).encode("utf-8")
        client.post("/webhooks/razorpay", content=b, headers={"X-Razorpay-Signature": _sign(b)})

    resp = client.get(f"/subscriptions/{sub_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["subscription_id"] == sub_id
    assert data["total_attempts"] == 2
    assert len(data["history"]) == 2
    assert data["history"][0]["attempt_number"] == 1
    assert data["history"][1]["attempt_number"] == 2


def test_unmapped_error_routes_to_out_of_scope_writeoff():
    """Unmapped or constructed error codes are rejected out of scope and written off by design."""
    sub_id = f"sub_oos_{int(datetime.now().timestamp() * 1000)}"
    payload = {
        "event": "payment.failed",
        "event_id": f"evt_{sub_id}_oos",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{sub_id}_oos",
                    "subscription_id": sub_id,
                    "amount": 29900,
                    "method": "card",
                    "error_reason": "BAD_REQUEST_PAYMENT_PRE_DEBIT_NOTICE_NOT_ACKED",
                }
            }
        },
    }
    b = json.dumps(payload).encode("utf-8")
    resp = client.post("/webhooks/razorpay", content=b, headers={"X-Razorpay-Signature": _sign(b)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"]["chosen_action"] == "stop_and_writeoff"
    assert data["decision"]["guard_triggered"] == "out_of_scope"


def test_boundary_parity_batch_and_webhook_at_all_attempt_counts():
    """
    Boundary proof: The SAME record at the SAME attempt_count produces the EXACT SAME action
    and guard on both the batch path (classify_and_decide) and webhook receiver path.
    Tests attempt_count 1, 2, 3, 4 across UPI (cap=3) and Card (cap=4).
    """
    for method, cap in [("upi", 3), ("card", 4)]:
        for att in (1, 2, 3, 4):
            rec_id = f"pay_boundary_{method}_{att}_{int(datetime.now().timestamp() * 1000)}"
            payment_obj = FailedPayment(
                id=rec_id,
                merchant_id="mid_boundary_01",
                customer_id="cust_boundary_01",
                amount_paise=199900,
                currency="INR",
                failure_reason="insufficient_funds",
                attempt_count=att,
                last_attempt_at=datetime.now(),
                payment_method=method,
                customer_ltv_paise=2500000,
                notes="Boundary parity verification test",
                payment_state="confirmed_failed",
            )
            # 1. Batch path decision
            batch_decision = classify_and_decide(payment_obj, use_llm=False)

            # 2. Webhook path decision
            webhook_payload = {
                "event": "payment.failed",
                "event_id": f"evt_{rec_id}",
                "account_id": payment_obj.merchant_id,
                "payload": {
                    "payment": {
                        "entity": {
                            "id": payment_obj.id,
                            "amount": payment_obj.amount_paise,
                            "currency": payment_obj.currency,
                            "method": payment_obj.payment_method,
                            "error_reason": payment_obj.failure_reason,
                            "attempt_count": att,
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
            wh_action = webhook_data["decision"]["chosen_action"]
            wh_guard = webhook_data["decision"].get("guard_triggered")

            assert wh_action == batch_decision.chosen_action, (
                f"Mismatch on {method} at attempt {att}: webhook got {wh_action}, batch got {batch_decision.chosen_action}"
            )
            assert wh_guard == batch_decision.guard_triggered, (
                f"Guard mismatch on {method} at attempt {att}: webhook got {wh_guard}, batch got {batch_decision.guard_triggered}"
            )


