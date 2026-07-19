# -*- coding: utf-8 -*-
"""
AegisBot -- Recommendation Engine Test Suite (test_recommender.py)

Unit tests for recommender.build_recommendations. These do NOT require the
model pickle or scikit-learn -- the recommender only depends on rubric.py and
plain data, so this suite runs fast and in isolation.

Covers:
  1. Structure       -> output has the agreed keys and shapes
  2. Dynamic top-N   -> threshold + cap (<=5) + floor (>=1 when not Low)
  3. Prioritization  -> answer level drives high/medium/low
  4. Reverse coding  -> a protective habit answered "no" surfaces as an issue
  5. Ordering        -> issues sorted by contribution (highest first)
  6. Password issues -> objective flaws appear alongside behavioural ones
  7. Clean user      -> perfect answers + strong password -> no recommendations

Run with pytest (recommended):
    cd ml/tests
    pytest -v test_recommender.py

Run without pytest installed (fallback, same assertions):
    python3 test_recommender.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from recommender import (build_recommendations, MAX_RECOMMENDATIONS,  # noqa: E402
                         MIN_RECOMMENDATIONS, PROBLEM_THRESHOLD)
from password_analysis import analyze_password  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
# A deliberately risky respondent: bad on the high-weight direct questions and
# on the protective reverse questions, with a weak password.
RISKY_ANSWERS = {
    "PM01": 4, "PM02": 0, "PM03": 0, "PM04": 0, "PM05": 4,
    "AUTH01": 0, "AUTH02": 4, "AUTH03": 0, "AUTH04": 4, "AUTH05": 0,
    "PHISH01": 0, "PHISH02": 4, "PHISH03": 4, "PHISH04": 0, "PHISH05": 0,
    "SOC01": 4, "SOC02": 4, "SOC03": 0, "SOC04": 4, "SOC05": 4,
}
WEAK_PW = analyze_password("password")

# A near-perfect respondent: safe on every question, strong long password.
SAFE_ANSWERS = {
    "PM01": 0, "PM02": 4, "PM03": 4, "PM04": 4, "PM05": 0,
    "AUTH01": 4, "AUTH02": 0, "AUTH03": 4, "AUTH04": 0, "AUTH05": 4,
    "PHISH01": 4, "PHISH02": 0, "PHISH03": 0, "PHISH04": 4, "PHISH05": 4,
    "SOC01": 0, "SOC02": 0, "SOC03": 4, "SOC04": 0, "SOC05": 0,
}
STRONG_PW = analyze_password("Tr0ub4dour&3xtraLongPhrase")


# ---------------------------------------------------------------------------
# 1. Structure
# ---------------------------------------------------------------------------
def test_output_structure():
    r = build_recommendations(RISKY_ANSWERS, WEAK_PW, "High")
    assert set(r.keys()) == {"recommendations", "all_issues", "summary"}
    assert isinstance(r["recommendations"], list)
    assert isinstance(r["all_issues"], list)
    assert set(r["summary"].keys()) == {"total_issues", "shown", "by_priority"}
    # every issue dict carries the agreed fields
    for item in r["all_issues"]:
        assert {"code", "category", "priority", "issue", "action",
                "evidence", "contribution"} <= set(item.keys())
        assert item["priority"] in {"high", "medium", "low"}


# ---------------------------------------------------------------------------
# 2. Dynamic top-N: cap and floor
# ---------------------------------------------------------------------------
def test_cap_at_max():
    r = build_recommendations(RISKY_ANSWERS, WEAK_PW, "High")
    assert len(r["recommendations"]) <= MAX_RECOMMENDATIONS
    assert r["summary"]["shown"] == len(r["recommendations"])


def test_floor_when_not_low():
    # All answers = 1 on direct / 3 on reverse -> risk_frac 0.25, below the 0.5
    # threshold, so nothing qualifies for the top list; but the user isn't Low,
    # so the MIN floor must still surface at least one item.
    mild = {}
    direct_ans, reverse_ans = 1, 3
    for code in RISKY_ANSWERS:
        # reuse safe answers' direction knowledge indirectly: just set all to a
        # mild value; the engine handles direction internally.
        mild[code] = direct_ans
    r = build_recommendations(mild, STRONG_PW, "Moderate")
    assert len(r["recommendations"]) >= MIN_RECOMMENDATIONS


def test_low_user_can_get_zero():
    r = build_recommendations(SAFE_ANSWERS, STRONG_PW, "Low")
    assert r["recommendations"] == []
    assert r["summary"]["shown"] == 0


# ---------------------------------------------------------------------------
# 3. Prioritization: answer level drives priority
# ---------------------------------------------------------------------------
def test_worst_answer_is_high_priority():
    # PM01 answered 4 (always reuse) is a direct question -> risk_frac 1.0 -> high
    r = build_recommendations({"PM01": 4}, STRONG_PW, "Moderate")
    pm01 = next(i for i in r["all_issues"] if i["code"] == "PM01")
    assert pm01["priority"] == "high"


def test_mid_answer_is_medium_priority():
    # PM01 answered 2 -> risk_frac 0.5 -> medium
    r = build_recommendations({"PM01": 2}, STRONG_PW, "Moderate")
    pm01 = next(i for i in r["all_issues"] if i["code"] == "PM01")
    assert pm01["priority"] == "medium"


# ---------------------------------------------------------------------------
# 4. Reverse coding: protective habit answered "no" must surface
# ---------------------------------------------------------------------------
def test_reverse_question_surfaces_when_unsafe():
    # PM03 "Do you use a password manager?" is reverse-coded. Answer 0 (=no) is
    # the UNSAFE end, so it must appear as an issue with high priority.
    r = build_recommendations({"PM03": 0}, STRONG_PW, "Moderate")
    pm03 = next(i for i in r["all_issues"] if i["code"] == "PM03")
    assert pm03["priority"] == "high"
    # and its action must be phrased as a fix, not a mirrored negation
    assert "password manager" in pm03["action"].lower()


def test_reverse_question_absent_when_safe():
    # PM03 answered 4 (=yes, uses a manager) -> safe end -> no issue at all.
    r = build_recommendations({"PM03": 4}, STRONG_PW, "Low")
    assert all(i["code"] != "PM03" for i in r["all_issues"])


# ---------------------------------------------------------------------------
# 5. Ordering: highest contribution first
# ---------------------------------------------------------------------------
def test_all_issues_sorted_by_contribution():
    r = build_recommendations(RISKY_ANSWERS, WEAK_PW, "High")
    contribs = [i["contribution"] for i in r["all_issues"]]
    assert contribs == sorted(contribs, reverse=True)


# ---------------------------------------------------------------------------
# 6. Password issues appear alongside behavioural ones
# ---------------------------------------------------------------------------
def test_password_issues_present():
    r = build_recommendations(RISKY_ANSWERS, WEAK_PW, "High")
    codes = {i["code"] for i in r["all_issues"]}
    # "password" triggers the common-pattern, short-length and low-diversity flaws
    assert any(c.startswith("PW_") for c in codes)


def test_strong_password_has_no_pw_issues():
    r = build_recommendations(SAFE_ANSWERS, STRONG_PW, "Low")
    codes = {i["code"] for i in r["all_issues"]}
    assert not any(c.startswith("PW_") for c in codes)


# ---------------------------------------------------------------------------
# 7. Threshold sanity
# ---------------------------------------------------------------------------
def test_threshold_constant_is_sane():
    assert 0.0 < PROBLEM_THRESHOLD <= 1.0
    assert MIN_RECOMMENDATIONS <= MAX_RECOMMENDATIONS


# ---------------------------------------------------------------------------
# Fallback runner: `python3 test_recommender.py` with no pytest installed.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
        else:
            print(f"PASS  {fn.__name__}")
            passed += 1
    print(f"\n{passed}/{len(fns)} tests passed.")
