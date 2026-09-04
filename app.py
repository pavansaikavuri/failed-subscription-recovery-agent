import os
import json
import sqlite3
import hmac
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

from models import FailedPayment, AuditEntry, InterventionDecision
from pipeline import classify_and_decide, log_audit_entry, POLICY_VERSION, DEDUPE_TTL_HOURS

load_dotenv(Path(__file__).parent / ".env")

app = FastAPI(
    title="Razorpay Subscription Recovery Webhook Receiver",
    version="1.0.0",
    description="FastAPI ingestion endpoint with HMAC-SHA256 signature verification and SQLite idempotency ledger."
)

DB_PATH = Path(__file__).parent / "webhook_events.db"
AUDIT_LOG_PATH = Path(__file__).parent / "audit_log.jsonl"
REPORT_PATH = Path(__file__).parent / "benchmark_report.html"


def init_db(db_path: Path = DB_PATH):
    """Initializes SQLite database with UNIQUE constraint on event_id."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT,
                received_at TIMESTAMP,
                payload TEXT
            )
            """
        )
        conn.commit()


# Initialize SQLite table on load
init_db()


def map_razorpay_payload_to_failed_payment(payload: Dict[str, Any], event_id: str) -> FailedPayment:
    """
    Normalizes a Razorpay webhook event payload into a FailedPayment domain object.
    Supports both payment.failed and subscription.halted event schemas.
    """
    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    subscription_entity = payload.get("payload", {}).get("subscription", {}).get("entity", {})

    # Extract ID
    record_id = payment_entity.get("id") or subscription_entity.get("id") or payload.get("id") or event_id

    # Extract merchant and customer IDs
    merchant_id = payload.get("account_id") or payment_entity.get("merchant_id") or "acc_live_demo"
    customer_id = payment_entity.get("customer_id") or payload.get("customer_id") or "cust_webhook_01"

    # Extract amount in paise
    amount_paise = payment_entity.get("amount") or payload.get("amount_paise") or 100000

    # Extract failure reason
    raw_reason = (
        payment_entity.get("error_reason")
        or payment_entity.get("failure_reason")
        or payload.get("failure_reason")
        or "gateway_timeout"
    )

    # Attempt count
    attempt_count = (
        payment_entity.get("attempt_count")
        or payment_entity.get("notes", {}).get("attempt_count")
        or payload.get("attempt_count", 1)
    )

    # Payment method
    payment_method = payment_entity.get("method") or payload.get("payment_method", "upi")

    # Customer LTV
    notes_dict = payment_entity.get("notes", {})
    ltv = notes_dict.get("customer_ltv_paise") if isinstance(notes_dict, dict) else 0
    if not ltv and isinstance(notes_dict, dict):
        ltv = notes_dict.get("customer_ltv", 0)
    customer_ltv_paise = ltv or payload.get("customer_ltv_paise", 0)

    # Notes string
    raw_notes = payment_entity.get("notes") or payload.get("notes")
    if isinstance(raw_notes, str):
        notes_str = raw_notes
    elif isinstance(raw_notes, dict):
        notes_str = raw_notes.get("notes") or raw_notes.get("description") or json.dumps(raw_notes)
    else:
        notes_str = payment_entity.get("description") or ""

    # Payment state (reconciliation guard check)
    payment_state = payment_entity.get("payment_state") or payload.get("payment_state", "confirmed_failed")

    # Subscription ID
    sub_id = subscription_entity.get("id") or payment_entity.get("subscription_id")

    return FailedPayment(
        id=record_id,
        merchant_id=merchant_id,
        customer_id=customer_id,
        amount_paise=amount_paise,
        currency="INR",
        failure_reason=raw_reason,
        attempt_count=attempt_count,
        last_attempt_at=datetime.now(),
        subscription_id=sub_id,
        payment_method=payment_method,
        customer_ltv_paise=customer_ltv_paise,
        notes=notes_str,
        payment_state=payment_state,
    )


@app.get("/health")
def get_health():
    return {
        "status": "ok",
        "service": "razorpay_recovery_webhook_receiver",
        "policy_version": POLICY_VERSION,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    if not REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Benchmark report not found. Run 'python pipeline.py --benchmark' to generate it."
        )
    content = REPORT_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


@app.get("/audit")
def get_audit():
    if not AUDIT_LOG_PATH.exists():
        return []
    entries = []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    return entries


@app.post("/webhooks/razorpay")
async def receive_razorpay_webhook(request: Request):
    # 1. HMAC-SHA256 Signature Verification
    signature = request.headers.get("X-Razorpay-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Razorpay-Signature header")

    body_bytes = await request.body()
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret_razorpay_2026")
    computed_sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_sig, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 2. Parse JSON Payload
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    event_id = payload.get("event_id") or payload.get("id")
    if not event_id:
        payment_ent = payload.get("payload", {}).get("payment", {}).get("entity", {})
        event_id = payment_ent.get("id") or f"evt_{hashlib.md5(body_bytes).hexdigest()[:12]}"

    event_type = payload.get("event", "payment.failed")
    now = datetime.now()

    # 3. Webhook Idempotency in SQLite with dedupe.ttl_hours
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT received_at FROM webhook_events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
        if row:
            try:
                last_received = datetime.fromisoformat(row[0])
                if (now - last_received) < timedelta(hours=DEDUPE_TTL_HOURS):
                    return JSONResponse(
                        status_code=200,
                        content={"status": "duplicate_suppressed", "event_id": event_id}
                    )
            except Exception:
                return JSONResponse(
                    status_code=200,
                    content={"status": "duplicate_suppressed", "event_id": event_id}
                )

        # Record event in SQLite
        cursor.execute(
            "INSERT OR REPLACE INTO webhook_events (event_id, event_type, received_at, payload) VALUES (?, ?, ?, ?)",
            (event_id, event_type, now.isoformat(), body_bytes.decode("utf-8"))
        )
        conn.commit()

    # 4. Map to FailedPayment domain model
    try:
        payment = map_razorpay_payload_to_failed_payment(payload, event_id=event_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to map Razorpay payload: {e}")

    # 5. Run shared decision engine (applies all 4 deterministic guards and strategy logic)
    decision = classify_and_decide(payment, use_llm=False)

    # 6. Append to audit_log.jsonl
    dec_source = getattr(decision, "decision_source", None) or ("guard" if getattr(decision, "guard_triggered", None) else "rules")
    mod_version = getattr(decision, "model_version", None) or ("guard-v1" if dec_source == "guard" else "rules-v1")
    guard_trig = getattr(decision, "guard_triggered", None)

    audit_entry = AuditEntry(
        timestamp=now,
        record_id=payment.id,
        failure_reason=payment.failure_reason,
        decision=decision,
        amount_at_risk_paise=payment.amount_paise,
        recovered_paise=0,
        status="escalated" if (decision.escalate or decision.chosen_action == "escalate_to_human") else (
            "written_off" if decision.chosen_action == "stop_and_writeoff" else "decision_made"
        ),
        cost_paise=0,
        violation=False,
        penalty_paise=0,
        model_version=mod_version,
        policy_version=POLICY_VERSION,
        decision_source=dec_source,
        guard_triggered=guard_trig,
    )
    log_audit_entry(audit_entry, out_path=str(AUDIT_LOG_PATH))

    # 7. Return decision as JSON
    return {
        "status": "decision_made",
        "event_id": event_id,
        "record_id": payment.id,
        "decision": decision.model_dump(),
    }
