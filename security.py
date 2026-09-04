import re
import base64
from typing import Tuple

# Primary regex patterns to detect prompt injection and instruction overrides
INJECTION_PATTERNS = [
    r"(?i)\bignore\s+(?:previous|prior|above)\s+instructions\b",
    r"(?i)\byou\s+are\s+now\b",
    r"(?i)\bsystem\s*:",
    r"(?i)\bnew\s+instructions\b",
    r"(?i)\bdisregard\b",
    r"(?i)\breturn\s+retry_now\b",
    r"(?i)\bconfidence\s+1\.0\b",
    r"\[SYSTEM\]",
    r"\[/SYSTEM\]",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"<system>",
    r"</system>",
]

COMPILED_PATTERNS = [re.compile(p) for p in INJECTION_PATTERNS]
BASE64_CANDIDATE_REGEX = re.compile(r"[A-Za-z0-9+/=]{20,}")


def _check_string_for_injection(text: str) -> bool:
    """Checks whether the given plaintext matches any injection pattern."""
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _check_base64_blobs(text: str) -> bool:
    """Finds candidate base64 sequences over 20 chars and checks if any decode to injection patterns."""
    candidates = BASE64_CANDIDATE_REGEX.findall(text)
    for cand in candidates:
        rem = len(cand) % 4
        padded = cand + ("=" * (4 - rem) if rem else "")
        try:
            decoded_bytes = base64.b64decode(padded, validate=True)
            decoded_str = decoded_bytes.decode("utf-8", errors="ignore")
            if len(decoded_str) >= 8 and _check_string_for_injection(decoded_str):
                return True
        except Exception:
            continue
    return False


def sanitize_notes(notes: str) -> Tuple[str, bool]:
    """
    Scans merchant notes for prompt injection attempts.
    Returns (sanitized_notes, is_injected).
    If injection detected: returns ('[notes withheld: injection pattern detected]', True).
    If benign: returns (notes, False).
    """
    if not notes or not isinstance(notes, str):
        return notes or "", False

    # Check direct patterns
    if _check_string_for_injection(notes):
        return "[notes withheld: injection pattern detected]", True

    # Check base64-encoded patterns
    if _check_base64_blobs(notes):
        return "[notes withheld: injection pattern detected]", True

    return notes, False
