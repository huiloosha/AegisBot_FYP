# -*- coding: utf-8 -*-
"""
Generates a synthetic, rubric-labeled dataset for AegisBot.

Design:
 - Each simulated respondent has a latent "security posture" trait per
   category (Normal distribution) that correlates their answers realistically
   (so the dataset isn't pure independent noise -> more realistic for ML).
 - Raw answers (0-4 ordinal) + password_analysis fields are the MODEL INPUT
   FEATURES (X).
 - The rubric in rubric.py converts those raw inputs into behaviour_score,
   password_score, overall_risk_score and risk_level -> these are the
   LABELS (y), not model inputs. (Feeding the rubric's own aggregate
   subscores back in as features would leak the label trivially.)
"""
import numpy as np
import pandas as pd
from rubric import (QUESTIONS, CATEGORY_WEIGHTS, PASSWORD_RUBRIC,
                     OVERALL_WEIGHTS, risk_level_from_score)

RNG_SEED = 42
N_RESPONDENTS = 650

COMMON_PATTERNS = ["123456", "password", "qwerty", "111111", "abc123", "letmein"]


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def sample_answers(rng, n):
    """Sample raw 0-4 answers for all 20 questions using per-category
    latent traits so answers within a category are correlated."""
    cats = list(CATEGORY_WEIGHTS.keys())
    # shared "general security awareness" trait + per-category deviation,
    # slightly biased toward risky (consistent with survey finding that most
    # respondents show moderate awareness but risky habits)
    general = rng.normal(-0.15, 1.0, size=n)
    latent = {c: general + rng.normal(-0.1, 0.9, size=n) for c in cats}

    data = {}
    for q in QUESTIONS:
        lat = latent[q["category"]]
        noise = rng.normal(0, 1.0, size=n)
        signal = lat + noise
        prob_safe = sigmoid(signal)  # higher => more "safe" leaning

        if q["response_type"] == "yes_no":
            # "yes" meaning depends on direction: for reverse-coded protective
            # questions, yes==safe(4); for direct-coded risky questions,
            # yes==risky(4)
            yes = (rng.random(n) < prob_safe).astype(int)
            if q["risk_direction"] == "reverse":
                vals = np.where(yes == 1, 4, 0)
            else:
                vals = np.where(yes == 1, 0, 4)  # "yes" to a risky Q flips
                # actually for direct yes_no risky questions, yes=risky=4
                vals = np.where(yes == 1, 4, 0)
                if q["code"] in ("PM05", "AUTH04", "PHISH03", "SOC05"):
                    # these are phrased so "yes" = risky regardless of prob_safe framing
                    yes_risky = (rng.random(n) < (1 - prob_safe)).astype(int)
                    vals = np.where(yes_risky == 1, 4, 0)
        else:
            # scale / frequency -> ordinal 0-4 via binned safe-probability
            raw = prob_safe if q["risk_direction"] == "reverse" else (1 - prob_safe)
            vals = np.clip(np.round(raw * 4 + rng.normal(0, 0.4, size=n)), 0, 4).astype(int)
        data[q["code"]] = vals
    return data


def sample_password_features(rng, n, pm_quality_proxy):
    """pm_quality_proxy: 0..4 array approximating PM04 (password complexity
    self-report) so objective password features correlate with self-reported
    habits, as would be expected in real respondents."""
    quality = (pm_quality_proxy / 4.0)  # 0..1

    length = np.clip(rng.normal(6.5 + quality * 5, 2.3, size=n), 4, 20).round().astype(int)
    has_upper = (rng.random(n) < (0.2 + 0.5 * quality)).astype(bool)
    has_lower = np.ones(n, dtype=bool)  # virtually all passwords contain lowercase
    has_number = (rng.random(n) < (0.45 + 0.35 * quality)).astype(bool)
    has_symbol = (rng.random(n) < (0.08 + 0.5 * quality)).astype(bool)

    common_pattern = (rng.random(n) < (0.45 - 0.35 * quality)).astype(bool)
    common_pattern &= (length <= 11)  # long passwords rarely pure common patterns
    repeated_chars = (rng.random(n) < (0.28 - 0.20 * quality)).astype(bool)

    # entropy estimate (bits) ~ log2(charset_size) * length, degraded by patterns
    charset = 26 + has_upper * 26 + has_number * 10 + has_symbol * 32
    charset = np.clip(charset, 26, 94)
    entropy = length * np.log2(charset)
    entropy = np.where(common_pattern, entropy * 0.25, entropy)
    entropy = np.where(repeated_chars, entropy * 0.7, entropy)
    entropy = entropy.round(1)

    return dict(
        password_length=length,
        has_uppercase=has_upper,
        has_lowercase=has_lower,
        has_number=has_number,
        has_symbol=has_symbol,
        common_pattern_detected=common_pattern,
        repeated_characters=repeated_chars,
        estimated_entropy=entropy,
    )


def score_behaviour(df):
    cat_scores = {}
    for cat, cat_w in CATEGORY_WEIGHTS.items():
        cat_qs = [q for q in QUESTIONS if q["category"] == cat]
        s = np.zeros(len(df))
        for q in cat_qs:
            raw = df[q["code"]].values.astype(float)
            norm = raw / 4.0
            risk_frac = norm if q["risk_direction"] == "direct" else (1 - norm)
            s += risk_frac * q["weight"] * 100.0
        cat_scores[cat] = s
    behaviour_score = np.zeros(len(df))
    for cat, cat_w in CATEGORY_WEIGHTS.items():
        behaviour_score += cat_scores[cat] * cat_w
    return cat_scores, behaviour_score


def score_password(df):
    r = PASSWORD_RUBRIC
    strength = np.clip(df["estimated_entropy"] / r["entropy_scale_bits"] * 100.0, 0, 100)
    diversity = (df["has_uppercase"].astype(int) + df["has_lowercase"].astype(int) +
                 df["has_number"].astype(int) + df["has_symbol"].astype(int))
    strength += np.clip(diversity * r["diversity_bonus_each"], 0, r["diversity_bonus_max"])
    strength -= np.where(df["common_pattern_detected"], r["common_pattern_penalty"], 0)
    strength -= np.where(df["repeated_characters"], r["repeated_char_penalty"], 0)
    strength -= np.where(df["password_length"] < r["short_length_threshold"],
                          r["short_length_penalty"], 0)
    strength = np.clip(strength, 0, 100)
    password_score = strength  # 0-100, higher = stronger/safer
    password_risk = 100 - password_score
    return password_score.round(1), password_risk.round(1)


def strength_label(score):
    return np.where(score >= 70, "Strong", np.where(score >= 40, "Moderate", "Weak"))


def build():
    rng = np.random.default_rng(RNG_SEED)
    answers = sample_answers(rng, N_RESPONDENTS)
    df = pd.DataFrame(answers)

    pw_feats = sample_password_features(rng, N_RESPONDENTS, pm_quality_proxy=df["PM04"].values)
    for k, v in pw_feats.items():
        df[k] = v

    cat_scores, behaviour_score = score_behaviour(df)
    password_score, password_risk = score_password(df)

    df["password_score"] = password_score
    df["strength_label"] = strength_label(password_score)

    for cat, s in cat_scores.items():
        df[f"{cat}_category_score"] = s.round(1)
    df["behaviour_score"] = behaviour_score.round(1)

    overall = (OVERALL_WEIGHTS["behaviour"] * df["behaviour_score"] +
               OVERALL_WEIGHTS["password"] * password_risk)
    df["overall_risk_score"] = overall.round(1)
    df["risk_probability"] = (df["overall_risk_score"] / 100.0).round(3)
    df["risk_level"] = df["overall_risk_score"].apply(risk_level_from_score)

    # user id + light metadata, matching the ERD's assessment grain
    df.insert(0, "assessment_id", np.arange(1, N_RESPONDENTS + 1))
    df["is_synthetic"] = True

    # column order: question answers, password features, then labels/scores
    q_cols = [q["code"] for q in QUESTIONS]
    pw_cols = list(pw_feats.keys())
    label_cols = (["password_score", "strength_label"] +
                  [f"{c}_category_score" for c in CATEGORY_WEIGHTS] +
                  ["behaviour_score", "overall_risk_score", "risk_probability",
                   "risk_level", "is_synthetic"])
    df = df[["assessment_id"] + q_cols + pw_cols + label_cols]
    return df


if __name__ == "__main__":
    df = build()

    out = "../data/AegisBot_Evidence-Based_Synthetic_Cyber_Risk_Dataset.csv"

    df.to_csv(out, index=False)

    print(df.shape)
    print(df["risk_level"].value_counts())
    print(df.head(3).T)
