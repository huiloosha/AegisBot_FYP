# -*- coding: utf-8 -*-
"""
AegisBot -- Recommendation Engine (recommender.py)

Turns a completed assessment into a personalized, prioritized security plan.

WHY THIS MODULE EXISTS
----------------------
/api/analyze already returns risk_class + probabilities, but that only tells the
user *how* risky they are, not *what to do about it*. This module derives the
"what to do" layer. It does NOT re-train or re-run the model. It re-reads the
same raw inputs (the 20 behavioural answers + the 8 password features) and maps
each weak spot to a concrete corrective action, ordered by how much that weak
spot contributes to risk.

CONSISTENCY WITH THE REST OF THE PIPELINE
-----------------------------------------
The per-question "risk contribution" uses the SAME normalization as
build_dataset.score_behaviour:

    risk_frac = answer/4            (direct-coded question)
    risk_frac = 1 - answer/4       (reverse-coded question)
    contribution = risk_frac * question_weight * CATEGORY_WEIGHTS[cat] * 100

So the ordering the user sees is consistent with the rubric the model was
trained on, not a separate ad-hoc heuristic.

Password contributions are derived from PASSWORD_RUBRIC penalties, rescaled onto
the same 0..100 axis so behavioural and password issues sort together in one
combined list.

DESIGN DECISIONS (agreed)
-------------------------
- Dynamic top-N with a threshold: `recommendations` contains every issue with
  risk_frac >= PROBLEM_THRESHOLD, capped at MAX_RECOMMENDATIONS, and at least
  MIN_RECOMMENDATIONS when the user is not already Low risk.
- Hybrid granularity: the answer LEVEL sets the priority (high/medium/low); the
  action TEXT is a single fix-oriented string per question (phrased toward the
  correction, which matters for reverse-coded questions).
- `all_issues`: the full sorted list is returned alongside the capped
  `recommendations`, so the frontend can show top-N and hide the rest behind a
  "show more".
"""
from rubric import QUESTIONS, CATEGORY_WEIGHTS, CATEGORY_NAMES, PASSWORD_RUBRIC

# ---------------------------------------------------------------------------
# 1. Tunable policy constants
# ---------------------------------------------------------------------------
# An answer is "a problem worth surfacing in the top list" when its risk_frac
# reaches this. risk_frac 0.5 == answer 2 on a direct question (or answer 2 on a
# reverse one), i.e. the mid-point. Below this it still appears in all_issues.
PROBLEM_THRESHOLD = 0.5

MAX_RECOMMENDATIONS = 5   # never overwhelm the user
MIN_RECOMMENDATIONS = 1   # if not Low, always give at least one thing to do

# Priority bands, keyed off risk_frac (the answer level).
#   >= 0.75  (answer 3-4 direct / 0-1 reverse) -> high
#   >= 0.50  (answer 2)                          -> medium
#   >  0.00  (answer 1 direct / 3 reverse)       -> low
PRIORITY_HIGH_CUTOFF = 0.75
PRIORITY_MEDIUM_CUTOFF = 0.50


def _priority_from_frac(risk_frac: float) -> str:
    if risk_frac >= PRIORITY_HIGH_CUTOFF:
        return "high"
    if risk_frac >= PRIORITY_MEDIUM_CUTOFF:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# 2. Corrective action text -- one fix-oriented line per question code.
#    Phrased toward the CORRECTION, not mirrored from the question, so that
#    reverse-coded items ("Do you use a password manager?") read as an
#    instruction ("Start using a password manager"), never as a negation.
# ---------------------------------------------------------------------------
ACTION_TEXT = {
    # Password Management
    "PM01": "Stop reusing passwords across accounts -- give every important "
            "account (email, banking) its own unique password first.",
    "PM02": "Change your passwords promptly whenever a service reports a breach, "
            "instead of leaving old credentials in place.",
    "PM03": "Start using a password manager to generate and store strong, unique "
            "passwords so you don't have to remember them.",
    "PM04": "Increase your password complexity -- aim for length and a mix of "
            "upper/lower case, numbers, and symbols.",
    "PM05": "Stop writing down or sharing your passwords; keep them in a password "
            "manager instead of on paper or in messages.",
    # Authentication / MFA
    "AUTH01": "Turn on Two-Factor/Multi-Factor Authentication (2FA/MFA) on your "
              "important accounts -- it blocks the large majority of takeovers.",
    "AUTH02": "Stop skipping 2FA prompts; complete them every time rather than "
              "dismissing them for convenience.",
    "AUTH03": "Enable biometric authentication (fingerprint/face) where it's "
              "offered to add a layer beyond your password.",
    "AUTH04": "Never share a one-time password (OTP) or verification code with "
              "anyone -- legitimate services will never ask for it.",
    "AUTH05": "Review your login-activity alerts regularly so you can catch an "
              "unauthorized sign-in early.",
    # Phishing & Awareness
    "PHISH01": "Build up your phishing-recognition skills -- learn the common "
               "red flags in suspicious emails and messages.",
    "PHISH02": "Stop clicking links from unknown or unexpected senders; verify "
               "the source before opening anything.",
    "PHISH03": "Never enter your credentials on unfamiliar or suspicious "
               "websites -- check the address bar and the site's legitimacy first.",
    "PHISH04": "Verify a sender's identity out-of-band before acting on urgent "
               "requests involving money or credentials.",
    "PHISH05": "Install software and app updates promptly when prompted to close "
               "known security holes.",
    # Social Media & Digital Footprint
    "SOC01": "Reduce the personal information (location, birthdate, workplace) "
             "you share publicly on social media.",
    "SOC02": "Stop accepting friend/connection requests from people you don't "
             "know -- it widens your attack surface.",
    "SOC03": "Review and tighten the privacy settings on your social media "
             "accounts to limit who can see your data.",
    "SOC04": "Avoid using public Wi-Fi without a VPN; assume unencrypted networks "
             "can be intercepted.",
    "SOC05": "Stop geotagging posts or sharing your real-time location publicly.",
}

# Short, user-facing description of the detected problem, per question code.
ISSUE_TEXT = {
    "PM01": "You reuse the same password across multiple accounts.",
    "PM02": "You don't update passwords promptly after breach notices.",
    "PM03": "You don't use a password manager.",
    "PM04": "Your passwords are not very complex.",
    "PM05": "You write down or share your passwords.",
    "AUTH01": "You don't consistently enable 2FA/MFA on important accounts.",
    "AUTH02": "You dismiss or skip 2FA prompts.",
    "AUTH03": "You don't use biometric authentication when available.",
    "AUTH04": "You have shared an OTP or verification code with someone.",
    "AUTH05": "You rarely review login-activity alerts.",
    "PHISH01": "You're not confident at identifying phishing.",
    "PHISH02": "You click links from unknown or unexpected senders.",
    "PHISH03": "You've entered credentials on a suspicious website.",
    "PHISH04": "You don't verify senders before acting on urgent requests.",
    "PHISH05": "You delay installing software/app updates.",
    "SOC01": "You share a lot of personal information publicly.",
    "SOC02": "You accept connection requests from strangers.",
    "SOC03": "You don't review your social media privacy settings.",
    "SOC04": "You use public Wi-Fi without a VPN.",
    "SOC05": "You share your real-time location publicly.",
}

# Fast lookup of the question metadata by code.
_Q_BY_CODE = {q["code"]: q for q in QUESTIONS}


# ---------------------------------------------------------------------------
# 3. Behavioural issues from the 20 answers
# ---------------------------------------------------------------------------
def _behavioural_issues(answers: dict) -> list[dict]:
    """One issue dict per answered question whose risk_frac > 0, i.e. any answer
    that is less than perfectly safe. Sorting/capping happens later."""
    issues = []
    for code, q in _Q_BY_CODE.items():
        if code not in answers:
            continue
        try:
            raw = float(answers[code])
        except (TypeError, ValueError):
            continue
        raw = max(0.0, min(raw, 4.0))
        norm = raw / 4.0
        risk_frac = norm if q["risk_direction"] == "direct" else (1.0 - norm)
        if risk_frac <= 0.0:
            continue  # a perfect answer -> nothing to recommend

        contribution = risk_frac * q["weight"] * CATEGORY_WEIGHTS[q["category"]] * 100.0
        issues.append({
            "code": code,
            "category": CATEGORY_NAMES[q["category"]],
            "priority": _priority_from_frac(risk_frac),
            "issue": ISSUE_TEXT[code],
            "action": ACTION_TEXT[code],
            "evidence": q["evidence"],
            "contribution": round(contribution, 2),
            "risk_frac": round(risk_frac, 3),
        })
    return issues


# ---------------------------------------------------------------------------
# 4. Password issues from the 8 objective features
# ---------------------------------------------------------------------------
# Each password issue is scored by its PASSWORD_RUBRIC penalty, rescaled onto the
# same 0..100 axis as behavioural contributions so the two sort together.
# The rescale factor keeps the biggest single password penalty comparable to a
# strong behavioural contribution rather than dwarfing it.
_PW_PENALTY_SCALE = 0.5  # 20-point penalty -> contribution 10.0, etc.


def _pw_priority(penalty: int) -> str:
    if penalty >= 15:
        return "high"
    if penalty >= 10:
        return "medium"
    return "low"


def _password_issues(pw: dict) -> list[dict]:
    r = PASSWORD_RUBRIC
    issues = []

    def add(code, penalty, issue, action, evidence):
        issues.append({
            "code": code,
            "category": "Password Strength",
            "priority": _pw_priority(penalty),
            "issue": issue,
            "action": action,
            "evidence": evidence,
            "contribution": round(penalty * _PW_PENALTY_SCALE, 2),
            "risk_frac": None,  # not applicable to objective password features
        })

    if pw.get("common_pattern_detected"):
        add("PW_COMMON_PATTERN", r["common_pattern_penalty"],
            "Your password contains a common, easily guessed pattern.",
            "Avoid common patterns like '123456' or 'qwerty'; use an "
            "unpredictable, randomly generated password.",
            "Common patterns are the first candidates in dictionary and "
            "credential-stuffing attacks.")

    if pw.get("password_length", 99) < r["short_length_threshold"]:
        add("PW_SHORT", r["short_length_penalty"],
            "Your password is shorter than the recommended minimum.",
            "Make your password at least 12 characters long; length is the "
            "single biggest factor in brute-force resistance.",
            "Short passwords fall quickly to brute-force attacks (NIST SP 800-63B).")

    if pw.get("repeated_characters"):
        add("PW_REPEATED", r["repeated_char_penalty"],
            "Your password has long runs of repeated characters.",
            "Avoid repeated character runs (e.g. 'aaa', '111'); they reduce "
            "effective randomness.",
            "Repeated-character runs lower entropy and are trivially guessable.")

    # Missing character classes -> encourage diversity. We surface this only when
    # two or more classes are missing, to avoid nagging about a single symbol.
    present = sum(bool(pw.get(k)) for k in
                  ("has_uppercase", "has_lowercase", "has_number", "has_symbol"))
    if present <= 2:
        missing_penalty = r["diversity_bonus_each"] * (4 - present)
        add("PW_LOW_DIVERSITY", missing_penalty,
            "Your password uses only a narrow set of character types.",
            "Mix upper- and lower-case letters, numbers, and symbols to widen "
            "the character set an attacker must search.",
            "A larger character set increases the search space for brute-force "
            "attacks.")

    return issues


# ---------------------------------------------------------------------------
# 5. Public entry point
# ---------------------------------------------------------------------------
def build_recommendations(answers: dict, password_features: dict,
                          risk_class: str | None = None) -> dict:
    """
    answers:            the 20 question codes (PM01..SOC05) -> 0-4.
    password_features:  the 8 objective password features (as produced by
                        analyze_password).
    risk_class:         optional predicted class ("Low"/"Moderate"/"High"),
                        used only to decide the MIN_RECOMMENDATIONS floor.

    Returns:
        {
          "recommendations": [ ...capped, prioritized... ],
          "all_issues":      [ ...every issue, sorted by contribution... ],
          "summary": {"total_issues": int, "shown": int,
                      "by_priority": {"high": int, "medium": int, "low": int}}
        }
    """
    issues = _behavioural_issues(answers) + _password_issues(password_features)

    # Highest contribution first; ties broken by priority ordering then code.
    _prio_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (-i["contribution"],
                               _prio_rank.get(i["priority"], 3),
                               i["code"]))

    # Build the capped top-N. Prefer issues at/above the problem threshold; if
    # none qualify but the user is not Low, still surface the single worst one.
    strong = [i for i in issues if (i["risk_frac"] is None
                                    or i["risk_frac"] >= PROBLEM_THRESHOLD)]
    if strong:
        top = strong[:MAX_RECOMMENDATIONS]
    else:
        top = []

    is_low = (risk_class == "Low")
    if not top and not is_low and issues:
        top = issues[:MIN_RECOMMENDATIONS]

    by_priority = {"high": 0, "medium": 0, "low": 0}
    for i in top:
        by_priority[i["priority"]] = by_priority.get(i["priority"], 0) + 1

    return {
        "recommendations": top,
        "all_issues": issues,
        "summary": {
            "total_issues": len(issues),
            "shown": len(top),
            "by_priority": by_priority,
        },
    }


if __name__ == "__main__":
    # Quick manual check against the sample assessment.
    import json
    from password_analysis import analyze_password

    sample_answers = {
        "PM01": 4, "PM02": 0, "PM03": 0, "PM04": 0, "PM05": 4,
        "AUTH01": 0, "AUTH02": 4, "AUTH03": 0, "AUTH04": 4, "AUTH05": 0,
        "PHISH01": 0, "PHISH02": 4, "PHISH03": 4, "PHISH04": 0, "PHISH05": 0,
        "SOC01": 4, "SOC02": 4, "SOC03": 0, "SOC04": 4, "SOC05": 4,
    }
    pw = analyze_password("password")
    print(json.dumps(build_recommendations(sample_answers, pw, "High"), indent=2))
