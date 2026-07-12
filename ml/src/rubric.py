# -*- coding: utf-8 -*-
"""
Evidence-based Cyber-Risk Scoring Rubric
AegisBot / Predictive Cyber-Risk Personal Assistant

This module is the single source of truth for:
 - the 20-item behavioural question bank (4 categories)
 - the password-analysis scoring rubric
 - the aggregation formula (category -> behaviour_score -> overall_risk_score)
 - the risk_level banding

It is imported by:
 - build_dataset.py      (labels the synthetic dataset)
 - build_workbook.py     (writes Feature Table + Risk Encoding Table sheets)
"""

# ---------------------------------------------------------------------------
# 1. CATEGORY WEIGHTS (must sum to 1.0) -> compose behaviour_score
# ---------------------------------------------------------------------------
CATEGORY_WEIGHTS = {
    "PM":    0.30,   # Password Management (self-reported habits)
    "AUTH":  0.25,   # Authentication / MFA
    "PHISH": 0.25,   # Phishing & Social-Engineering Awareness
    "SOC":   0.20,   # Social Media & Digital Footprint Exposure
}

CATEGORY_NAMES = {
    "PM":    "Password Management",
    "AUTH":  "Authentication / MFA",
    "PHISH": "Phishing & Awareness",
    "SOC":   "Social Media Exposure",
}

# ---------------------------------------------------------------------------
# 2. QUESTION BANK
# each question: code, category, text, response_type, risk_direction,
#                weight (within its category, weights per category sum to 1.0),
#                evidence
# risk_direction:
#   "direct"  -> higher raw answer (0-4) = higher risk
#   "reverse" -> higher raw answer (0-4) = protective / lower risk
# ---------------------------------------------------------------------------
QUESTIONS = [
    # --- Password Management (PM) ---------------------------------------
    dict(code="PM01", category="PM", weight=0.25, response_type="scale",
         risk_direction="direct",
         text="How often do you reuse the same password across multiple accounts?",
         evidence="Password reuse is the single strongest predictor of credential-stuffing "
                   "compromise (Nwakeze et al., 2025; NIST SP 800-63B)."),
    dict(code="PM02", category="PM", weight=0.15, response_type="frequency",
         risk_direction="reverse",
         text="How often do you change/update your passwords after a service breach notice?",
         evidence="Timely credential rotation reduces exposure window (NIST SP 800-63B)."),
    dict(code="PM03", category="PM", weight=0.25, response_type="yes_no",
         risk_direction="reverse",
         text="Do you use a password manager to generate/store passwords?",
         evidence="Password managers correlate with higher-entropy, unique passwords "
                   "(Folino et al., 2023)."),
    dict(code="PM04", category="PM", weight=0.20, response_type="scale",
         risk_direction="reverse",
         text="How complex are the passwords you typically create (length/character mix)?",
         evidence="Composition/length strongly affects brute-force resistance (NIST SP 800-63B)."),
    dict(code="PM05", category="PM", weight=0.15, response_type="yes_no",
         risk_direction="direct",
         text="Do you write down or share your passwords with other people?",
         evidence="Manual sharing/storage bypasses technical controls (OWASP ASVS v4)."),

    # --- Authentication / MFA (AUTH) -------------------------------------
    dict(code="AUTH01", category="AUTH", weight=0.30, response_type="yes_no",
         risk_direction="reverse",
         text="Do you enable Two-Factor/Multi-Factor Authentication (2FA/MFA) on important accounts?",
         evidence="MFA blocks ~99% of automated account-takeover attempts (Microsoft/NIST)."),
    dict(code="AUTH02", category="AUTH", weight=0.20, response_type="frequency",
         risk_direction="direct",
         text="How often do you dismiss or skip 2FA prompts when they are offered?",
         evidence="Inconsistent MFA adoption identified as a key risk gap in the survey findings."),
    dict(code="AUTH03", category="AUTH", weight=0.15, response_type="yes_no",
         risk_direction="reverse",
         text="Do you use biometric authentication (fingerprint/face) when available?",
         evidence="Biometric factors add a possession/inherence layer beyond passwords."),
    dict(code="AUTH04", category="AUTH", weight=0.20, response_type="yes_no",
         risk_direction="direct",
         text="Have you ever shared a one-time password (OTP) or verification code with someone else?",
         evidence="OTP sharing is a common social-engineering / SIM-swap vector (Hassan et al., 2025)."),
    dict(code="AUTH05", category="AUTH", weight=0.15, response_type="frequency",
         risk_direction="reverse",
         text="How often do you review login-activity alerts for your accounts?",
         evidence="Active monitoring shortens detection time for account compromise (UEBA literature)."),

    # --- Phishing & Awareness (PHISH) ------------------------------------
    dict(code="PHISH01", category="PHISH", weight=0.25, response_type="scale",
         risk_direction="reverse",
         text="How confident are you in identifying phishing emails or messages?",
         evidence="Self-assessed phishing literacy correlates with click-through resistance "
                   "(Mihailescu et al., 2023)."),
    dict(code="PHISH02", category="PHISH", weight=0.25, response_type="frequency",
         risk_direction="direct",
         text="How often do you click links from unknown or unexpected senders?",
         evidence="Link-clicking behaviour is the dominant phishing success factor."),
    dict(code="PHISH03", category="PHISH", weight=0.25, response_type="yes_no",
         risk_direction="direct",
         text="Have you ever entered your credentials on a suspicious or unfamiliar website?",
         evidence="Direct historical indicator of susceptibility to credential-harvesting sites."),
    dict(code="PHISH04", category="PHISH", weight=0.15, response_type="yes_no",
         risk_direction="reverse",
         text="Do you verify a sender's identity before acting on urgent requests (money, credentials)?",
         evidence="Out-of-band verification is a core anti-BEC/anti-phishing control."),
    dict(code="PHISH05", category="PHISH", weight=0.10, response_type="frequency",
         risk_direction="reverse",
         text="How often do you install software/app updates when prompted?",
         evidence="Patch latency is a recognised exploitability factor (Adabala, 2021)."),

    # --- Social Media & Digital Footprint Exposure (SOC) ------------------
    dict(code="SOC01", category="SOC", weight=0.25, response_type="scale",
         risk_direction="direct",
         text="How much personal information (location, birthdate, workplace) do you share "
              "publicly on social media?",
         evidence="Public PII exposure enables targeted social engineering (Wishvaranga et al., 2024)."),
    dict(code="SOC02", category="SOC", weight=0.20, response_type="frequency",
         risk_direction="direct",
         text="Do you accept friend/connection requests from people you don't know?",
         evidence="Unknown-contact acceptance widens the social-engineering attack surface."),
    dict(code="SOC03", category="SOC", weight=0.20, response_type="frequency",
         risk_direction="reverse",
         text="Do you review and adjust the privacy settings on your social media accounts?",
         evidence="Active privacy management reduces the exploitable digital footprint."),
    dict(code="SOC04", category="SOC", weight=0.20, response_type="frequency",
         risk_direction="direct",
         text="How often do you use public Wi-Fi without a VPN?",
         evidence="Unencrypted public networks enable traffic interception (Blancaflor et al., 2025)."),
    dict(code="SOC05", category="SOC", weight=0.15, response_type="yes_no",
         risk_direction="direct",
         text="Do you geotag posts or share your real-time location publicly?",
         evidence="Real-time location sharing is a known physical/digital safety risk indicator."),
]

assert abs(sum(CATEGORY_WEIGHTS.values()) - 1.0) < 1e-9
for cat in CATEGORY_WEIGHTS:
    s = sum(q["weight"] for q in QUESTIONS if q["category"] == cat)
    assert abs(s - 1.0) < 1e-9, f"{cat} weights sum to {s}, expected 1.0"

# ---------------------------------------------------------------------------
# 3. PASSWORD-ANALYSIS RUBRIC (objective, computed from password_analysis fields)
# password_strength_score (0-100), higher = stronger/safer
# ---------------------------------------------------------------------------
PASSWORD_RUBRIC = {
    "entropy_scale_bits": 60,     # bits considered "full marks" baseline (NIST-aligned)
    "diversity_bonus_each": 5,    # + points per character class present (upper/lower/digit/symbol)
    "diversity_bonus_max": 20,
    "common_pattern_penalty": 20, # deduction if a known weak pattern is detected (e.g. "12345", "qwerty")
    "repeated_char_penalty": 10,  # deduction for long repeated-character runs
    "short_length_penalty": 15,   # deduction if password_length < 8
    "short_length_threshold": 8,
}

# ---------------------------------------------------------------------------
# 4. AGGREGATION + RISK BANDING
# ---------------------------------------------------------------------------
OVERALL_WEIGHTS = {
    "behaviour": 0.60,   # self-reported behavioural risk
    "password":  0.40,   # objective password-strength risk
}

RISK_LEVEL_THRESHOLDS = {
    "Low":      (0, 39.999),
    "Moderate": (40, 69.999),
    "High":     (70, 100),
}


def risk_level_from_score(score: float) -> str:
    for level, (lo, hi) in RISK_LEVEL_THRESHOLDS.items():
        if lo <= score <= hi:
            return level
    return "High" if score > 100 else "Low"
