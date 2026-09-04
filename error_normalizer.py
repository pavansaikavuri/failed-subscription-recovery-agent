"""
Razorpay Error Code Normalizer

This module normalizes external Razorpay payment gateway error codes and error reasons 
into the internal 9-reason taxonomy used by the recovery decision engine:
    1. insufficient_funds
    2. gateway_timeout
    3. mandate_not_registered
    4. mandate_lapsed_on_reissue
    5. issuer_declined
    6. expired_card
    7. risk_block
    8. pre_debit_notice_not_acked
    9. network_failure

CRITICAL ARCHITECTURAL NOTE ON PARTIAL MAPPING:
This mapping is INTENTIONALLY PARTIAL. It maps only genuine, verified error codes 
and error reasons documented in Razorpay's public API documentation:
- https://razorpay.com/docs/errors/
- https://razorpay.com/docs/errors/payments/cards/
- https://razorpay.com/docs/errors/payments/upi/
- https://razorpay.com/docs/errors/common/

VERIFIED RAZORPAY CODES INCLUDED:
- 'card_declined' -> 'issuer_declined' (Razorpay Cards Doc: "The payment was declined by the customer's bank...")
- 'payment_declined' -> 'issuer_declined' (Razorpay UPI Doc: "The payment did not go through because the funds could not be debited...")
- 'card_expired' -> 'expired_card' (Razorpay Cards Doc: "The payment could not be completed because the customer's card is expired.")
- 'payment_timed_out' -> 'gateway_timeout' (Razorpay Cards & UPI Docs: "The payment could not be completed as the customer exceeded the time limit...")
- 'gateway_technical_error' -> 'network_failure' (Razorpay Cards & UPI Docs: "There was a downtime on our partner bank...")
- 'bank_technical_error' -> 'network_failure' (Razorpay Cards & UPI Docs: "There was a downtime on the customer's bank...")
- 'payment_risk_check_failed' -> 'risk_block' (Razorpay Cards Doc: "The transaction was unsuccessful as the customer's bank declined the payment, citing it as fraudulent.")
- 'gateway_error' -> 'gateway_timeout' (Razorpay Common Errors Doc: Top-level error class code 'GATEWAY_ERROR')

ELIMINATED / EXCLUDED CODES (NOT INCLUDED):
- 'BAD_REQUEST_PAYMENT_MANDATE_NOT_REGISTERED' (Constructed by analogy; not in public docs)
- 'BAD_REQUEST_PAYMENT_MANDATE_LAPSED' (Constructed by analogy; not in public docs)
- 'BAD_REQUEST_PAYMENT_PRE_DEBIT_NOTICE_NOT_ACKED' (Constructed by analogy; pre-debit notices are regulatory notifications, not gateway error codes)
- 'BAD_REQUEST_PAYMENT_UPI_PIN_FAILED' (Constructed by analogy; not in public docs)
- Identity mappings like 'insufficient_funds' -> 'insufficient_funds' (Omitted; identity mapping internal strings is padding, not normalization)

DESIGN PRINCIPLE:
Any unmapped, unrecognized, or internal code returns None. In the webhook receiver 
and recovery pipeline, unmapped errors are routed to out-of-scope rejection 
(guard_triggered="out_of_scope") by design, rather than guessing or fabricating 
unknown gateway behavior.
"""

from typing import Optional, Dict

# Strictly verified Razorpay public documentation codes mapping to internal taxonomy.
# Note: Zero identity mappings included.
VERIFIED_RAZORPAY_ERROR_MAP: Dict[str, str] = {
    # Cards errors (razorpay.com/docs/errors/payments/cards)
    "card_declined": "issuer_declined",
    "card_expired": "expired_card",
    "payment_risk_check_failed": "risk_block",
    
    # UPI errors (razorpay.com/docs/errors/payments/upi)
    "payment_declined": "issuer_declined",
    
    # Shared Cards & UPI timeout / technical downtime
    "payment_timed_out": "gateway_timeout",
    "gateway_technical_error": "network_failure",
    "bank_technical_error": "network_failure",
    
    # High-level error class (razorpay.com/docs/errors/common)
    "gateway_error": "gateway_timeout",
}


def normalize_razorpay_error(raw_code: Optional[str]) -> Optional[str]:
    """
    Normalizes an external Razorpay error code/reason to internal recovery taxonomy.
    
    Case-insensitive lookup against verified documentation codes.
    Returns None if the code is not in the verified mapping table.
    """
    if not raw_code or not isinstance(raw_code, str):
        return None
    
    cleaned = raw_code.strip().lower()
    return VERIFIED_RAZORPAY_ERROR_MAP.get(cleaned)
