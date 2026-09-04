"""
Razorpay Error Code Normalizer

This module normalizes external Razorpay payment gateway error codes and error reasons 
into the internal 9-reason taxonomy defined by models.FailedPayment:
    1. mandate_not_registered
    2. afa_required_not_completed
    3. upi_pin_failure
    4. insufficient_funds
    5. card_expired
    6. issuer_declined
    7. gateway_timeout
    8. mandate_lapsed_on_reissue
    9. pre_debit_notice_not_acked

CRITICAL ARCHITECTURAL NOTE ON PARTIAL MAPPING:
This mapping is INTENTIONALLY PARTIAL. It maps only genuine, verified error codes 
and error reasons documented in Razorpay's public API documentation:
- https://razorpay.com/docs/errors/
- https://razorpay.com/docs/errors/payments/cards/
- https://razorpay.com/docs/errors/payments/upi/
- https://razorpay.com/docs/errors/common/

VERIFIED RAZORPAY CODES INCLUDED:
- 'card_declined' -> 'issuer_declined'
  (Razorpay Cards Doc: "The payment was declined by the customer's bank, resulting in the transaction being unsuccessful.")
- 'card_expired' -> 'card_expired'
  (Razorpay Cards Doc: "The payment could not be completed because the customer's card is expired.")
- 'payment_timed_out' -> 'gateway_timeout'
  (Razorpay Cards & UPI Docs: "The payment could not be completed as the customer exceeded the time limit for payment processing.")
- 'gateway_technical_error' -> 'gateway_timeout'
  (Razorpay Cards & UPI Docs: "There was a downtime on our partner bank due to which the payment has failed.")
- 'bank_technical_error' -> 'gateway_timeout'
  (Razorpay Cards & UPI Docs: "There was a downtime on the customer's bank due to which the payment has failed.")
- 'gateway_error' -> 'gateway_timeout'
  (Razorpay Common Errors Doc: Top-level error class code 'GATEWAY_ERROR')

DELIBERATELY EXCLUDED CODES (ROUTED TO OUT-OF-SCOPE BY DESIGN):
- 'payment_declined': Excluded. The UPI doc cites "funds could not be debited from the customer's bank account", 
  which conflates insufficient balance with general debit failures without balance proof. Dropped rather than guessing.
- 'payment_risk_check_failed': Excluded. Customer bank fraud rejections have no corresponding enum in our 9-reason taxonomy 
  (no 'risk_block'). Dropped rather than inventing taxonomy strings, allowing it to route safely to out-of-scope write-off.
- 'BAD_REQUEST_PAYMENT_MANDATE_NOT_REGISTERED': Excluded (constructed by analogy; not in public gateway docs).
- 'BAD_REQUEST_PAYMENT_MANDATE_LAPSED': Excluded (constructed by analogy; not in public gateway docs).
- 'BAD_REQUEST_PAYMENT_PRE_DEBIT_NOTICE_NOT_ACKED': Excluded (regulatory workflow concept, not gateway error code).
- 'BAD_REQUEST_PAYMENT_UPI_PIN_FAILED': Excluded (constructed by analogy; not in public gateway docs).
- 'insufficient_funds -> insufficient_funds': Excluded (identity mapping internal string is padding, not normalization).

DESIGN PRINCIPLE:
Every target string in this mapping MUST exist within models.FailedPayment's failure_reason Literal.
Any unmapped or unrecognized code returns None. In the webhook receiver and recovery pipeline, 
unmapped errors are routed to out-of-scope rejection (guard_triggered="out_of_scope") by design, 
never guessing or fabricating unknown gateway behavior.
"""

from typing import Optional, Dict

# Strictly verified Razorpay public documentation codes mapping to the 9 internal reasons.
# Every target value is strictly validated against models.FailedPayment's failure_reason.
VERIFIED_RAZORPAY_ERROR_MAP: Dict[str, str] = {
    # Cards errors (razorpay.com/docs/errors/payments/cards)
    "card_declined": "issuer_declined",
    "card_expired": "card_expired",
    
    # Shared Cards & UPI timeout / technical downtime (razorpay.com/docs/errors/payments/cards & upi)
    "payment_timed_out": "gateway_timeout",
    "gateway_technical_error": "gateway_timeout",
    "bank_technical_error": "gateway_timeout",
    
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
