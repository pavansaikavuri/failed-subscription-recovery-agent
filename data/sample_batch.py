import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

# Ensure utf-8 encoding for console output on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from datetime import datetime, timedelta
from models import FailedPayment

now = datetime(2026, 8, 31, 23, 30, 0)

BATCH = [
    # 1-5: Base realistic sample rows
    {
        "id": "pay_Kx91aBcDeFgH10",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_8f3a2b",
        "amount_paise": 49900,  # ₹499
        "currency": "INR",
        "failure_reason": "upi_pin_failure",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(minutes=15),
        "subscription_id": "sub_Nx82kLmOpQrS01",
        "payment_method": "upi",
        "customer_ltv_paise": 1500000,  # ₹15,000
        "notes": "Recurring monthly SaaS subscription renewal",
    },
    {
        "id": "pay_Ly82bCdEfGhI21",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_9e4c3d",
        "amount_paise": 149900,  # ₹1,499
        "currency": "INR",
        "failure_reason": "insufficient_funds",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=4),
        "subscription_id": "sub_Ox93lMnPqRsT02",
        "payment_method": "upi",
        "customer_ltv_paise": 4500000,  # ₹45,000
        "notes": "Annual OTT streaming pack auto-debit",
    },
    {
        "id": "pay_Mz73cDeFgHiJ32",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_2b1a9f",
        "amount_paise": 499900,  # ₹4,999
        "currency": "INR",
        "failure_reason": "card_expired",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(days=1),
        "subscription_id": "sub_Py04mNoQrStU03",
        "payment_method": "card",
        "customer_ltv_paise": 8500000,  # ₹85,000
        "notes": "Gym membership quarterly billing - card expiry 08/26",
    },
    {
        "id": "pay_Na64dEfGhIjK43",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_5c8d7e",
        "amount_paise": 19900,  # ₹199
        "currency": "INR",
        "failure_reason": "mandate_not_registered",
        "attempt_count": 3,
        "last_attempt_at": now - timedelta(hours=12),
        "subscription_id": "sub_Qz15nOpRsTuV04",
        "payment_method": "upi",
        "customer_ltv_paise": 19900,  # ₹199
        "notes": "First recurring billing attempt after trial period",
    },
    {
        "id": "pay_Ob55eFgHiJkL54",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_7d6e5a",
        "amount_paise": 299900,  # ₹2,999
        "currency": "INR",
        "failure_reason": "gateway_timeout",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(minutes=45),
        "subscription_id": "sub_Ra26oPqStUvW05",
        "payment_method": "card",
        "customer_ltv_paise": 3600000,  # ₹36,000
        "notes": "E-learning course monthly EMI installment",
    },
    # 6-8: Specific failure mode test triggers
    {
        "id": "pay_Ex66fGhIjKlM65",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_3c9e1a",
        "amount_paise": 89900,  # ₹899
        "currency": "INR",
        "failure_reason": "insufficient_funds",
        "attempt_count": 5,  # Retry Exhaustion #1
        "last_attempt_at": now - timedelta(days=3),
        "subscription_id": "sub_Sb37pQrStUvW06",
        "payment_method": "upi",
        "customer_ltv_paise": 120000,
        "notes": "Fifth consecutive auto-debit failure after repeated retries",
    },
    {
        "id": "pay_Un77gHiJkLmM76",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_1a2b3c",
        "amount_paise": 249900,  # ₹2,499
        "currency": "INR",
        "failure_reason": "crypto_wallet_declined",  # Out-of-scope #1
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=2),
        "subscription_id": "sub_Tc48qRsTuVwX07",
        "payment_method": "crypto",
        "customer_ltv_paise": 500000,
        "notes": "Attempted off-rail payment method unsupported by mandate engine",
    },
    {
        "id": "pay_Lc88hIjKlMnN87",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_9z8y7x",
        "amount_paise": 199900,  # ₹1,999
        "currency": "INR",
        "failure_reason": "issuer_declined",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=6),
        "subscription_id": "sub_Ud59rStUvWxY08",
        "payment_method": "card",
        "customer_ltv_paise": 150000,
        "notes": "Bank returned generic decline code 005. Customer vehemently disputes charge as unauthorized fraud.",
    },
    # 9-12: Additional Retry Exhaustion & Out-of-Scope triggers
    {
        "id": "pay_Ex09iJkLmNoP98",
        "merchant_id": "mid_razor_33",
        "customer_id": "cust_4d7e2f",
        "amount_paise": 699900,  # ₹6,999
        "currency": "INR",
        "failure_reason": "issuer_declined",
        "attempt_count": 4,  # Retry Exhaustion #2
        "last_attempt_at": now - timedelta(days=2),
        "subscription_id": "sub_Ve60sTuVwXyZ09",
        "payment_method": "card",
        "customer_ltv_paise": 2800000,
        "notes": "Card issuer persistently blocked auto-debit; max retries exceeded",
    },
    {
        "id": "pay_Ex10jKlMnOpQ09",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_6b8a3c",
        "amount_paise": 34900,  # ₹349
        "currency": "INR",
        "failure_reason": "upi_pin_failure",
        "attempt_count": 4,  # Retry Exhaustion #3
        "last_attempt_at": now - timedelta(days=1),
        "subscription_id": "sub_Wf71tUvWxYzA10",
        "payment_method": "upi",
        "customer_ltv_paise": 69800,
        "notes": "User consistently failed to input UPI PIN despite 4 notifications",
    },
    {
        "id": "pay_Ex11kLmNoPqR10",
        "merchant_id": "mid_razor_55",
        "customer_id": "cust_7f9c4d",
        "amount_paise": 999900,  # ₹9,999
        "currency": "INR",
        "failure_reason": "gateway_timeout",
        "attempt_count": 5,  # Retry Exhaustion #4
        "last_attempt_at": now - timedelta(days=4),
        "subscription_id": "sub_Xg82uVwXyZaB11",
        "payment_method": "card",
        "customer_ltv_paise": 5999400,
        "notes": "Acquiring bank timeout repeated on 5 attempts across 4 days",
    },
    {
        "id": "pay_Un12lMnOpQrS21",
        "merchant_id": "mid_razor_22",
        "customer_id": "cust_2e5b8a",
        "amount_paise": 129900,  # ₹1,299
        "currency": "INR",
        "failure_reason": "cheque_bounce_physical",  # Out-of-scope #2
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=8),
        "subscription_id": "sub_Yh93vWxYzaBC12",
        "payment_method": "offline",
        "customer_ltv_paise": 389700,
        "notes": "Manual NACH paper clearing bounced due to drawer signature mismatch",
    },
    # 13-20: Diverse Indian Subscription Failure Reasons
    {
        "id": "pay_In13mNoPqRsT32",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_3a6c9e",
        "amount_paise": 29900,  # ₹299
        "currency": "INR",
        "failure_reason": "afa_required_not_completed",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(minutes=30),
        "subscription_id": "sub_Zi04wXyzaBCD13",
        "payment_method": "card",
        "customer_ltv_paise": 89700,
        "notes": "RBI Additional Factor of Authentication OTP screen abandoned by customer",
    },
    {
        "id": "pay_In14nOpQrStU43",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_8b4d1f",
        "amount_paise": 79900,  # ₹799
        "currency": "INR",
        "failure_reason": "pre_debit_notice_not_acked",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=24),
        "subscription_id": "sub_Aj15xYzaBCDE14",
        "payment_method": "upi",
        "customer_ltv_paise": 239700,
        "notes": "24-hour mandatory pre-debit SMS or notification not acknowledged by user",
    },
    {
        "id": "pay_In15oPqStUvW54",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_9c5e2a",
        "amount_paise": 849000,  # ₹8,490
        "currency": "INR",
        "failure_reason": "mandate_lapsed_on_reissue",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(days=2),
        "subscription_id": "sub_Bk26yZaBCDEF15",
        "payment_method": "card",
        "customer_ltv_paise": 5094000,
        "notes": "Customer replaced card on file but failed to approve updated e-mandate",
    },
    {
        "id": "pay_In16pQrStUvW65",
        "merchant_id": "mid_razor_33",
        "customer_id": "cust_1d6f3b",
        "amount_paise": 59900,  # ₹599
        "currency": "INR",
        "failure_reason": "upi_pin_failure",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=5),
        "subscription_id": "sub_Cl37zAbCDEFG16",
        "payment_method": "upi",
        "customer_ltv_paise": 179700,
        "notes": "Customer entered incorrect UPI MPIN twice during recurring prompt",
    },
    {
        "id": "pay_In17qRsTuVwX76",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_4e7a4c",
        "amount_paise": 199900,  # ₹1,999
        "currency": "INR",
        "failure_reason": "insufficient_funds",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=1),
        "subscription_id": "sub_Dm48aBcDEFGH17",
        "payment_method": "upi",
        "customer_ltv_paise": 799600,
        "notes": "Salary day cycle debit - end of month balance depleted",
    },
    {
        "id": "pay_In18rStUvWxY87",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_5f8b5d",
        "amount_paise": 399900,  # ₹3,999
        "currency": "INR",
        "failure_reason": "card_expired",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(days=1),
        "subscription_id": "sub_En59bCdEFGHI18",
        "payment_method": "card",
        "customer_ltv_paise": 2399400,
        "notes": "HDFC credit card expired 08/2026",
    },
    {
        "id": "pay_In19sTuVwXyZ98",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_6a9c6e",
        "amount_paise": 24900,  # ₹249
        "currency": "INR",
        "failure_reason": "gateway_timeout",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(minutes=20),
        "subscription_id": "sub_Fo60cDeFGHIJ19",
        "payment_method": "upi",
        "customer_ltv_paise": 49800,
        "notes": "NPCI switch timeout during peak evening traffic",
    },
    {
        "id": "pay_In20tUvWxYzA09",
        "merchant_id": "mid_razor_55",
        "customer_id": "cust_7b0d7f",
        "amount_paise": 450000,  # ₹4,500
        "currency": "INR",
        "failure_reason": "issuer_declined",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=3),
        "subscription_id": "sub_Gp71dEfGHIJK20",
        "payment_method": "card",
        "customer_ltv_paise": 1800000,
        "notes": "ICICI Bank declined transaction - international e-commerce disabled",
    },
    # 21-30: Scaling rows across SaaS, EdTech, Fitness, Media
    {
        "id": "pay_In21uVwXyZaB10",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_8c1e8a",
        "amount_paise": 99900,  # ₹999
        "currency": "INR",
        "failure_reason": "mandate_not_registered",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=7),
        "subscription_id": "sub_Hq82eFgHIJKL21",
        "payment_method": "upi",
        "customer_ltv_paise": 99900,
        "notes": "Initial auto-debit attempt before bank registration completed",
    },
    {
        "id": "pay_In22vWxYzaBC21",
        "merchant_id": "mid_razor_33",
        "customer_id": "cust_9d2f9b",
        "amount_paise": 199900,  # ₹1,999
        "currency": "INR",
        "failure_reason": "afa_required_not_completed",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=14),
        "subscription_id": "sub_Ir93fGhIJKLM22",
        "payment_method": "card",
        "customer_ltv_paise": 1199400,
        "notes": "Amount threshold requirement triggered AFA challenge",
    },
    {
        "id": "pay_In23wXyzaBCD32",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_1e3a0c",
        "amount_paise": 299900,  # ₹2,999
        "currency": "INR",
        "failure_reason": "insufficient_funds",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=18),
        "subscription_id": "sub_Js04gHiJKLMN23",
        "payment_method": "upi",
        "customer_ltv_paise": 3598800,
        "notes": "High-value quarterly coaching plan debit failed",
    },
    {
        "id": "pay_In24xYzaBCDE43",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_2f4b1d",
        "amount_paise": 49900,  # ₹499
        "currency": "INR",
        "failure_reason": "upi_pin_failure",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(minutes=50),
        "subscription_id": "sub_Kt15hIjKLMNO24",
        "payment_method": "upi",
        "customer_ltv_paise": 299400,
        "notes": "User cancelled UPI mandate execution on phone prompt",
    },
    {
        "id": "pay_In25yZaBCDEF54",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_3a5c2e",
        "amount_paise": 149900,  # ₹1,499
        "currency": "INR",
        "failure_reason": "card_expired",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(days=2),
        "subscription_id": "sub_Lu26iJkLMNOP25",
        "payment_method": "card",
        "customer_ltv_paise": 1499000,
        "notes": "Corporate card re-issuance pending",
    },
    {
        "id": "pay_In26zAbCDEFG65",
        "merchant_id": "mid_razor_55",
        "customer_id": "cust_4b6d3f",
        "amount_paise": 749900,  # ₹7,499
        "currency": "INR",
        "failure_reason": "gateway_timeout",
        "attempt_count": 3,
        "last_attempt_at": now - timedelta(hours=6),
        "subscription_id": "sub_Mv37jKlMNOPQ26",
        "payment_method": "card",
        "customer_ltv_paise": 4499400,
        "notes": "State Bank of India payment gateway temporary outage",
    },
    {
        "id": "pay_In27aBcDEFGH76",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_5c7e4a",
        "amount_paise": 69900,  # ₹699
        "currency": "INR",
        "failure_reason": "pre_debit_notice_not_acked",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=28),
        "subscription_id": "sub_Nw48kLmNOPQR27",
        "payment_method": "upi",
        "customer_ltv_paise": 419400,
        "notes": "SMS delivery failed due to DND registry on customer telecom line",
    },
    {
        "id": "pay_In28bCdEFGHI87",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_6d8f5b",
        "amount_paise": 19900,  # ₹199
        "currency": "INR",
        "failure_reason": "mandate_not_registered",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=9),
        "subscription_id": "sub_Ox59lMnOPQRS28",
        "payment_method": "upi",
        "customer_ltv_paise": 39800,
        "notes": "UPI handle switched from @okaxis to @okhdfcbank without re-auth",
    },
    {
        "id": "pay_In29cDeFGHIJ98",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_7e9a6c",
        "amount_paise": 349900,  # ₹3,499
        "currency": "INR",
        "failure_reason": "issuer_declined",
        "attempt_count": 3,
        "last_attempt_at": now - timedelta(hours=16),
        "subscription_id": "sub_Py60mNoPQRST29",
        "payment_method": "card",
        "customer_ltv_paise": 2099400,
        "notes": "Axis Bank fraud prevention velocity rule triggered",
    },
    {
        "id": "pay_In30dEfGHIJK09",
        "merchant_id": "mid_razor_33",
        "customer_id": "cust_8f0b7d",
        "amount_paise": 54900,  # ₹549
        "currency": "INR",
        "failure_reason": "upi_pin_failure",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(minutes=10),
        "subscription_id": "sub_Qz71nOpQRSTU30",
        "payment_method": "upi",
        "customer_ltv_paise": 164700,
        "notes": "User biometric failed on PhonePe app during auto-prompt",
    },
    # 31-40: Final scaling rows
    {
        "id": "pay_In31eFgHIJKL10",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_9a1c8e",
        "amount_paise": 899900,  # ₹8,999
        "currency": "INR",
        "failure_reason": "mandate_lapsed_on_reissue",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(days=1),
        "subscription_id": "sub_Ra82oPqRSTUV31",
        "payment_method": "card",
        "customer_ltv_paise": 5399400,
        "notes": "Executive annual membership renewal - card renewed with new CVV",
    },
    {
        "id": "pay_In32fGhIJKLM21",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_1b2d9f",
        "amount_paise": 119900,  # ₹1,199
        "currency": "INR",
        "failure_reason": "insufficient_funds",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=2),
        "subscription_id": "sub_Sb93pQrSTUVW32",
        "payment_method": "upi",
        "customer_ltv_paise": 1199000,
        "notes": "End-of-month account sweep caused temporary deficit",
    },
    {
        "id": "pay_In33gHiJKLMN32",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_2c3e0a",
        "amount_paise": 44900,  # ₹449
        "currency": "INR",
        "failure_reason": "gateway_timeout",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(minutes=35),
        "subscription_id": "sub_Tc04qRsTUVWX33",
        "payment_method": "upi",
        "customer_ltv_paise": 89800,
        "notes": "Yes Bank UPI server latency surge",
    },
    {
        "id": "pay_In34hIjKLMNO43",
        "merchant_id": "mid_razor_55",
        "customer_id": "cust_3d4f1b",
        "amount_paise": 199900,  # ₹1,999
        "currency": "INR",
        "failure_reason": "card_expired",
        "attempt_count": 3,
        "last_attempt_at": now - timedelta(days=2),
        "subscription_id": "sub_Ud15rStUVWXY34",
        "payment_method": "card",
        "customer_ltv_paise": 1599200,
        "notes": "Kotak Mahindra card expired last month; notification pending",
    },
    {
        "id": "pay_In35iJkLMNOP54",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_4e5a2c",
        "amount_paise": 29900,  # ₹299
        "currency": "INR",
        "failure_reason": "afa_required_not_completed",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=11),
        "subscription_id": "sub_Ve26sTuVWXYZ35",
        "payment_method": "card",
        "customer_ltv_paise": 149500,
        "notes": "3DS page session timed out before OTP entry",
    },
    {
        "id": "pay_In36jKlMNOPQ65",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_5f6b3d",
        "amount_paise": 79900,  # ₹799
        "currency": "INR",
        "failure_reason": "mandate_not_registered",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=15),
        "subscription_id": "sub_Wf37tUvWXYZa36",
        "payment_method": "upi",
        "customer_ltv_paise": 239700,
        "notes": "Paytm Payments Bank migration issue with recurring token",
    },
    {
        "id": "pay_In37kLmNOPQR76",
        "merchant_id": "mid_razor_91",
        "customer_id": "cust_6a7c4e",
        "amount_paise": 159900,  # ₹1,599
        "currency": "INR",
        "failure_reason": "pre_debit_notice_not_acked",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=22),
        "subscription_id": "sub_Xg48uVwXYZab37",
        "payment_method": "upi",
        "customer_ltv_paise": 959400,
        "notes": "WhatsApp pre-debit notice unread",
    },
    {
        "id": "pay_In38lMnOPQRS87",
        "merchant_id": "mid_razor_33",
        "customer_id": "cust_7b8d5f",
        "amount_paise": 649900,  # ₹6,499
        "currency": "INR",
        "failure_reason": "issuer_declined",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=8),
        "subscription_id": "sub_Yh59vWxYZabc38",
        "payment_method": "card",
        "customer_ltv_paise": 3899400,
        "notes": "Daily limit reached on IndusInd debit card",
    },
    {
        "id": "pay_In39mNoPQRST98",
        "merchant_id": "mid_razor_44",
        "customer_id": "cust_8c9e6a",
        "amount_paise": 99900,  # ₹999
        "currency": "INR",
        "failure_reason": "insufficient_funds",
        "attempt_count": 3,
        "last_attempt_at": now - timedelta(hours=19),
        "subscription_id": "sub_Zi60wXyZabcd39",
        "payment_method": "upi",
        "customer_ltv_paise": 499500,
        "notes": "Third debit failure for cloud backup subscription",
    },
    {
        "id": "pay_In40nOpQRSTU09",
        "merchant_id": "mid_razor_12",
        "customer_id": "cust_9d0f7b",
        "amount_paise": 49900,  # ₹499
        "currency": "INR",
        "failure_reason": "upi_pin_failure",
        "attempt_count": 3,
        "last_attempt_at": now - timedelta(hours=4),
        "subscription_id": "sub_Aj71xYzaBCde40",
        "payment_method": "upi",
        "customer_ltv_paise": 598800,
        "notes": "GPay UPI PIN retry exhausted on device, fallback required",
    },
    # 41-43: High-Value Escalation Threshold Records (>₹50,000)
    {
        "id": "pay_Hv41aBcDeFgH10",
        "merchant_id": "mid_razor_99",
        "customer_id": "cust_hv01",
        "amount_paise": 8500000,  # ₹85,000
        "currency": "INR",
        "failure_reason": "gateway_timeout",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=2),
        "subscription_id": "sub_Hv81aBcDeFgH41",
        "payment_method": "card",
        "customer_ltv_paise": 25500000,  # ₹2,55,000
        "notes": "Annual enterprise SaaS platform subscription renewal",
        "payment_state": "confirmed_failed",
    },
    {
        "id": "pay_Hv42bCdEfGhI21",
        "merchant_id": "mid_razor_99",
        "customer_id": "cust_hv02",
        "amount_paise": 6200000,  # ₹62,000
        "currency": "INR",
        "failure_reason": "insufficient_funds",
        "attempt_count": 2,
        "last_attempt_at": now - timedelta(hours=6),
        "subscription_id": "sub_Hv82bCdEfGhI42",
        "payment_method": "upi",
        "customer_ltv_paise": 18600000,  # ₹1,86,000
        "notes": "Annual executive leadership cohort plan auto-debit",
        "payment_state": "confirmed_failed",
    },
    {
        "id": "pay_Hv43cDeFgHiJ32",
        "merchant_id": "mid_razor_88",
        "customer_id": "cust_hv03",
        "amount_paise": 12000000,  # ₹1,20,000
        "currency": "INR",
        "failure_reason": "mandate_not_registered",
        "attempt_count": 1,
        "last_attempt_at": now - timedelta(hours=1),
        "subscription_id": "sub_Hv83cDeFgHiJ43",
        "payment_method": "card",
        "customer_ltv_paise": 50000000,  # ₹5,00,000
        "notes": "Enterprise multi-seat cloud license annual renewal",
        "payment_state": "confirmed_failed",
    },
]

if __name__ == "__main__":
    print(f"Total rows in BATCH: {len(BATCH)}")
    valid_count = 0
    invalid_count = 0
    for row in BATCH:
        try:
            print(FailedPayment(**row))
            valid_count += 1
        except Exception as e:
            print(f"[{row.get('id')}] (Out-of-scope/Malformed record caught in test): {row.get('failure_reason')}")
            invalid_count += 1
    print(f"\nValidated: {valid_count} valid rows, {invalid_count} out-of-scope test rows.")
