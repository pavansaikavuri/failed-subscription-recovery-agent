import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from error_normalizer import normalize_razorpay_error, VERIFIED_RAZORPAY_ERROR_MAP


def test_documented_codes_map_correctly():
    """Verified codes from Razorpay public documentation map to correct internal reasons."""
    assert normalize_razorpay_error("card_declined") == "issuer_declined"
    assert normalize_razorpay_error("payment_declined") == "issuer_declined"
    assert normalize_razorpay_error("card_expired") == "expired_card"
    assert normalize_razorpay_error("payment_timed_out") == "gateway_timeout"
    assert normalize_razorpay_error("gateway_technical_error") == "network_failure"
    assert normalize_razorpay_error("bank_technical_error") == "network_failure"
    assert normalize_razorpay_error("payment_risk_check_failed") == "risk_block"
    assert normalize_razorpay_error("gateway_error") == "gateway_timeout"


def test_unknown_and_constructed_codes_rejected_as_none():
    """Constructed analogies and unmapped codes return None to trigger out-of-scope rejection."""
    # Constructed codes that do NOT exist in public docs must return None
    assert normalize_razorpay_error("BAD_REQUEST_PAYMENT_PRE_DEBIT_NOTICE_NOT_ACKED") is None
    assert normalize_razorpay_error("BAD_REQUEST_PAYMENT_MANDATE_NOT_REGISTERED") is None
    assert normalize_razorpay_error("BAD_REQUEST_PAYMENT_MANDATE_LAPSED") is None
    assert normalize_razorpay_error("BAD_REQUEST_PAYMENT_UPI_PIN_FAILED") is None
    assert normalize_razorpay_error("some_unknown_gateway_error_code") is None
    assert normalize_razorpay_error("") is None
    assert normalize_razorpay_error(None) is None


def test_case_insensitivity_and_whitespace():
    """Normalization is case-insensitive and trims whitespace."""
    assert normalize_razorpay_error("  CARD_DECLINED  ") == "issuer_declined"
    assert normalize_razorpay_error("GATEWAY_ERROR") == "gateway_timeout"
    assert normalize_razorpay_error("Payment_Timed_Out") == "gateway_timeout"
    assert normalize_razorpay_error("Card_Expired") == "expired_card"
