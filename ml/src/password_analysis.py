# -*- coding: utf-8 -*-
"""
Password analysis — turn a raw password string into the 8 objective password
features the model was trained on.

WHY THIS MUST MATCH build_dataset.py EXACTLY
--------------------------------------------
The synthetic training set in build_dataset.py did not contain real password
strings — it *sampled* the boolean features and then computed estimated_entropy
with a specific formula (charset sizing + pattern/repeat degradation). The model
learned from entropy values produced by THAT formula.

So at inference time we must compute estimated_entropy with the identical formula,
or the number we feed the model will be on a different scale than it learned from.
The formula below is copied line-for-line (in intent) from
build_dataset.sample_password_features:

    charset = 26 + has_upper*26 + has_number*10 + has_symbol*32   (clipped 26..94)
    entropy = length * log2(charset)
    entropy *= 0.25   if common_pattern_detected
    entropy *= 0.70   if repeated_characters
    entropy = round(entropy, 1)

The ONLY difference: the booleans and pattern/repeat flags are now DETECTED from
a real string instead of randomly sampled. has_lowercase in the training data was
always True ("virtually all passwords contain lowercase"); here we detect it
honestly from the string.

COMMON_PATTERNS is the same list used to label the dataset, so "common pattern"
means the same thing at train and inference time.
"""
import math
import re

# Same list build_dataset.py used to define what a "common pattern" is.
COMMON_PATTERNS = ["123456", "password", "qwerty", "111111", "abc123", "letmein"]

# Charset sizes per character class — must match build_dataset.py.
_CHARSET_LOWER = 26
_CHARSET_UPPER = 26
_CHARSET_DIGIT = 10
_CHARSET_SYMBOL = 32
_CHARSET_MIN = 26
_CHARSET_MAX = 94

_COMMON_PATTERN_FACTOR = 0.25
_REPEATED_CHARS_FACTOR = 0.70

# The 8 password feature keys the model expects (subset of the full 28).
PASSWORD_FEATURE_KEYS = [
    "password_length",
    "estimated_entropy",
    "has_uppercase",
    "has_lowercase",
    "has_number",
    "has_symbol",
    "common_pattern_detected",
    "repeated_characters",
]


def _detect_common_pattern(password: str) -> bool:
    """True if any known weak pattern appears in the password (case-insensitive).

    Mirrors the dataset's notion of a common pattern. We also cap at length <= 11
    the way build_dataset did (long passwords are rarely pure common patterns),
    so a known pattern buried inside a long passphrase isn't over-penalised.
    """
    if len(password) > 11:
        return False
    low = password.lower()
    return any(pat in low for pat in COMMON_PATTERNS)


def _detect_repeated_characters(password: str) -> bool:
    """True if the password has a run of 3+ identical characters in a row
    (e.g. 'aaa', '111'). A simple, defensible definition of a repeated-char run.
    """
    return re.search(r"(.)\1\1", password) is not None


def analyze_password(password: str) -> dict:
    """
    Compute the 8 objective password features from a raw password string.

    Returns a dict with exactly PASSWORD_FEATURE_KEYS. Booleans are real Python
    bools; predict.py converts them to 0/1 before feeding the model.

    Raises ValueError on an empty password (nothing to analyse).
    """
    if password is None or password == "":
        raise ValueError("password must be a non-empty string.")

    length = len(password)

    has_uppercase = any(c.isupper() for c in password)
    has_lowercase = any(c.islower() for c in password)
    has_number = any(c.isdigit() for c in password)
    # "symbol" = any visible character that isn't a letter or a digit.
    has_symbol = any((not c.isalnum()) and (not c.isspace()) for c in password)

    common_pattern_detected = _detect_common_pattern(password)
    repeated_characters = _detect_repeated_characters(password)

    # --- entropy: identical formula to build_dataset.sample_password_features ---
    charset = (
        _CHARSET_LOWER
        + (_CHARSET_UPPER if has_uppercase else 0)
        + (_CHARSET_DIGIT if has_number else 0)
        + (_CHARSET_SYMBOL if has_symbol else 0)
    )
    charset = max(_CHARSET_MIN, min(charset, _CHARSET_MAX))

    entropy = length * math.log2(charset)
    if common_pattern_detected:
        entropy *= _COMMON_PATTERN_FACTOR
    if repeated_characters:
        entropy *= _REPEATED_CHARS_FACTOR
    entropy = round(entropy, 1)

    return {
        "password_length": length,
        "estimated_entropy": entropy,
        "has_uppercase": has_uppercase,
        "has_lowercase": has_lowercase,
        "has_number": has_number,
        "has_symbol": has_symbol,
        "common_pattern_detected": common_pattern_detected,
        "repeated_characters": repeated_characters,
    }


def password_strength_score(features: dict) -> float:
    """Compute the 0-100 password strength score (higher = stronger/safer) from
    the 8 objective features, using the SAME rubric as build_dataset.score_password.

    This is the objective password_score persisted in password_analysis. It is a
    label-side/reporting value -- NOT one of the 28 model input features -- so it
    lives here next to the features it is derived from rather than in the model.

    Formula (identical to build_dataset.score_password):
        strength  = clip(entropy / entropy_scale_bits * 100, 0, 100)
        strength += clip(n_char_classes * diversity_bonus_each, 0, diversity_bonus_max)
        strength -= common_pattern_penalty   if common_pattern_detected
        strength -= repeated_char_penalty     if repeated_characters
        strength -= short_length_penalty      if password_length < short_length_threshold
        strength  = clip(strength, 0, 100)
    """
    # Imported here (not at module top) so analyze_password stays dependency-light
    # for callers that only need the 8 features.
    from rubric import PASSWORD_RUBRIC as r

    entropy = float(features.get("estimated_entropy", 0) or 0)
    strength = max(0.0, min(entropy / r["entropy_scale_bits"] * 100.0, 100.0))

    diversity = sum(int(bool(features.get(k))) for k in
                    ("has_uppercase", "has_lowercase", "has_number", "has_symbol"))
    strength += min(diversity * r["diversity_bonus_each"], r["diversity_bonus_max"])

    if features.get("common_pattern_detected"):
        strength -= r["common_pattern_penalty"]
    if features.get("repeated_characters"):
        strength -= r["repeated_char_penalty"]
    if float(features.get("password_length", 0) or 0) < r["short_length_threshold"]:
        strength -= r["short_length_penalty"]

    strength = max(0.0, min(strength, 100.0))
    return round(strength, 1)


if __name__ == "__main__":
    # Quick manual check: python password_analysis.py
    import json
    for pw in ["password", "Tr0ub4dour&3xtra", "aaa111", "Xy9$"]:
        print(pw, "->", json.dumps(analyze_password(pw)))
