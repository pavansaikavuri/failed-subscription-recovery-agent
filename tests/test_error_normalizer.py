import sys
from pathlib import Path
from typing import get_args

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from error_normalizer import normalize_razorpay_error, VERIFIED_RAZORPAY_ERROR_MAP
from models import FailedPayment


def test_taxonomy_contract_every_mapping_target_is_valid_model_literal():
    """
    Contract test: EVERY target value in VERIFIED_RAZORPAY_ERROR_MAP must be
    a valid member of the 9-reason failure_reason Literal in models.FailedPayment.
    Derives the valid set dynamically from the Pydantic model annotation, never hardcoded.
    """
    model_valid_reasons = set(get_args(FailedPayment.model_fields["failure_reason"].annotation))
    
    assert len(model_valid_reasons) == 9, f"Expected exactly 9 reasons in FailedPayment taxonomy, got {len(model_valid_reasons)}"
    
    for input_code, target_reason in VERIFIED_RAZORPAY_ERROR_MAP.items():
        assert target_reason in model_valid_reasons, (
            f"Contract violation: Mapping '{input_code}' -> '{target_reason}' emits a string "
            f"not present in models.FailedPayment taxonomy ({model_valid_reasons})"
        )


def test_documented_codes_map_correctly():
    """Verified codes from Razorpay public documentation map to correct internal taxonomy reasons."""
    assert normalize_razorpay_error("card_declined") == "issuer_declined"
    assert normalize_razorpay_error("card_expired") == "card_expired"
    assert normalize_razorpay_error("payment_timed_out") == "gateway_timeout"
    assert normalize_razorpay_error("gateway_technical_error") == "gateway_timeout"
    assert normalize_razorpay_error("bank_technical_error") == "gateway_timeout"
    assert normalize_razorpay_error("gateway_error") == "gateway_timeout"


def test_unknown_and_constructed_codes_rejected_as_none():
    """Constructed analogies, unmapped, and deliberately dropped codes return None to trigger out-of-scope rejection."""
    # Constructed analogies
    assert normalize_razorpay_error("BAD_REQUEST_PAYMENT_PRE_DEBIT_NOTICE_NOT_ACKED") is None
    assert normalize_razorpay_error("BAD_REQUEST_PAYMENT_MANDATE_NOT_REGISTERED") is None
    assert normalize_razorpay_error("BAD_REQUEST_PAYMENT_MANDATE_LAPSED") is None
    assert normalize_razorpay_error("BAD_REQUEST_PAYMENT_UPI_PIN_FAILED") is None
    
    # Deliberately excluded codes (ambiguous debit failure or unmapped fraud category)
    assert normalize_razorpay_error("payment_declined") is None
    assert normalize_razorpay_error("payment_risk_check_failed") is None
    
    # Arbitrary strings and null inputs
    assert normalize_razorpay_error("some_unknown_gateway_error_code") is None
    assert normalize_razorpay_error("") is None
    assert normalize_razorpay_error(None) is None


def test_case_insensitivity_and_whitespace():
    """Normalization is case-insensitive and trims whitespace."""
    assert normalize_razorpay_error("  CARD_DECLINED  ") == "issuer_declined"
    assert normalize_razorpay_error("GATEWAY_ERROR") == "gateway_timeout"
    assert normalize_razorpay_error("Payment_Timed_Out") == "gateway_timeout"
    assert normalize_razorpay_error("Card_Expired") == "card_expired"
    assert normalize_razorpay_error("  bank_technical_error\n") == "gateway_timeout"
