# -*- coding: utf-8 -*-
"""
AegisBot — ML Test Suite (test_ml.py)

Covers four levels of testing, matching the FYP report structure:
  1. Data validation        -> dataset integrity checks
  2. Rubric / labeling logic -> unit tests on rubric.py's scoring rules
  3. Model performance        -> Accuracy/Precision/Recall/F1 vs. thresholds + baseline
  4. Inference / integration -> predict.py happy-path, failure-path, consistency checks

Run with pytest (recommended):
    cd ml/tests
    pytest -v test_ml.py

Run without pytest installed (fallback, same assertions):
    python3 test_ml.py
"""
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rubric import QUESTIONS, CATEGORY_WEIGHTS, risk_level_from_score  # noqa: E402
from build_dataset import score_behaviour  # noqa: E402
from train import load_data, FEATURE_COLS, TARGET_COL, RANDOM_STATE  # noqa: E402
from predict import predict_risk, find_best_model, load_bundle  # noqa: E402

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / \
    "AegisBot_Evidence-Based_Synthetic_Cyber_Risk_Dataset.csv"
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "best_model.pkl"

# Minimum acceptable performance for the saved best_model.pkl on the held-out
# test split. These are deliberately set below the SVM's observed ~0.90-0.91,
# so the suite fails loudly if a future retrain regresses badly, without being
# so tight that ordinary run-to-run noise trips it.
MIN_ACCURACY = 0.75
MIN_F1_MACRO = 0.75

# ---------------------------------------------------------------------------
# Cached loaders (avoid re-reading the CSV / re-loading the model per test)
# ---------------------------------------------------------------------------
_df_cache = None
_bundle_cache = None
_split_cache = None


def get_df():
    global _df_cache
    if _df_cache is None:
        _df_cache = pd.read_csv(DATA_PATH)
    return _df_cache


def get_bundle():
    global _bundle_cache
    if _bundle_cache is None:
        _bundle_cache = load_bundle(MODEL_PATH)
    return _bundle_cache


def get_test_split():
    """Recreates the exact same train/test split train.py used (same
    random_state, test_size, stratify), so we evaluate the saved model on
    the same held-out rows it was originally reported on."""
    global _split_cache
    if _split_cache is None:
        X, y = load_data(DATA_PATH)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
        )
        _split_cache = (X_train, X_test, y_train, y_test)
    return _split_cache


# ===========================================================================
# LEVEL 1 — DATA VALIDATION TESTING
# ===========================================================================
def test_dataset_file_exists():
    assert DATA_PATH.is_file(), f"Dataset not found at {DATA_PATH}"


def test_dataset_shape():
    df = get_df()
    assert df.shape[0] > 0, "Dataset has zero rows"
    assert df.shape[1] == 40, f"Expected 40 columns, got {df.shape[1]}"


def test_no_missing_values():
    df = get_df()
    nulls = df.isnull().sum()
    bad_cols = nulls[nulls > 0]
    assert bad_cols.empty, f"Found nulls in columns: {bad_cols.to_dict()}"


def test_risk_level_values_are_valid():
    df = get_df()
    valid = {"Low", "Moderate", "High"}
    found = set(df["risk_level"].unique())
    assert found <= valid, f"Unexpected risk_level values: {found - valid}"


def test_question_answers_in_range():
    df = get_df()
    q_cols = [q["code"] for q in QUESTIONS]
    for c in q_cols:
        out_of_range = df[(df[c] < 0) | (df[c] > 4)]
        assert out_of_range.empty, f"{c} has {len(out_of_range)} value(s) outside 0-4"


def test_no_duplicate_assessment_ids():
    df = get_df()
    dupes = df["assessment_id"].duplicated().sum()
    assert dupes == 0, f"Found {dupes} duplicate assessment_id values"


def test_all_rows_flagged_synthetic():
    df = get_df()
    assert (df["is_synthetic"] == True).all(), (  # noqa: E712
        "Not all rows are flagged is_synthetic=True — dataset naming/claims "
        "would be inaccurate if real rows are mixed in silently."
    )


def test_class_distribution_not_degenerate():
    df = get_df()
    counts = df["risk_level"].value_counts()
    assert len(counts) == 3, f"Expected all 3 classes present, found {len(counts)}"
    smallest_share = counts.min() / counts.sum()
    assert smallest_share > 0.05, (
        f"Smallest class is only {smallest_share:.1%} of the dataset — too "
        f"imbalanced for reliable macro-averaged metrics"
    )


# ===========================================================================
# LEVEL 2 — RUBRIC / LABELING LOGIC TESTING
# ===========================================================================
def _make_row(all_safe: bool):
    row = {}
    for q in QUESTIONS:
        if all_safe:
            row[q["code"]] = 4 if q["risk_direction"] == "reverse" else 0
        else:
            row[q["code"]] = 0 if q["risk_direction"] == "reverse" else 4
    return row


def test_all_safe_answers_score_zero_and_low():
    df = pd.DataFrame([_make_row(all_safe=True)])
    _, behaviour_score = score_behaviour(df)
    assert abs(behaviour_score[0] - 0.0) < 1e-6
    assert risk_level_from_score(behaviour_score[0]) == "Low"


def test_all_risky_answers_score_hundred_and_high():
    df = pd.DataFrame([_make_row(all_safe=False)])
    _, behaviour_score = score_behaviour(df)
    assert abs(behaviour_score[0] - 100.0) < 1e-6
    assert risk_level_from_score(behaviour_score[0]) == "High"


def test_risk_band_boundaries_are_half_open():
    # Low: [0, 40)   Moderate: [40, 70)   High: [70, 100]
    assert risk_level_from_score(0.0) == "Low"
    assert risk_level_from_score(39.9) == "Low"
    assert risk_level_from_score(40.0) == "Moderate"
    assert risk_level_from_score(69.9) == "Moderate"
    assert risk_level_from_score(70.0) == "High"
    assert risk_level_from_score(100.0) == "High"


def test_category_weights_sum_to_one():
    total = sum(CATEGORY_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Category weights sum to {total}, expected 1.0"


def test_question_weights_sum_to_one_per_category():
    for cat in CATEGORY_WEIGHTS:
        total = sum(q["weight"] for q in QUESTIONS if q["category"] == cat)
        assert abs(total - 1.0) < 1e-9, f"{cat} question weights sum to {total}, expected 1.0"


def test_every_question_has_valid_risk_direction():
    for q in QUESTIONS:
        assert q["risk_direction"] in ("direct", "reverse"), (
            f"{q['code']} has invalid risk_direction: {q['risk_direction']}"
        )


# ===========================================================================
# LEVEL 3 — MODEL PERFORMANCE TESTING
# ===========================================================================
def test_best_model_file_exists():
    assert MODEL_PATH.is_file(), f"best_model.pkl not found at {MODEL_PATH} — run train.py first"


def test_best_model_bundle_has_required_metadata():
    bundle = get_bundle()
    for key in ("model", "model_name", "feature_columns", "classes"):
        assert key in bundle, f"best_model.pkl missing expected key: {key}"
    assert bundle["feature_columns"] == FEATURE_COLS, (
        "Saved feature_columns don't match train.py's current FEATURE_COLS — "
        "model may be stale relative to the current pipeline."
    )


def test_model_accuracy_above_threshold():
    bundle = get_bundle()
    _, X_test, _, y_test = get_test_split()
    y_pred = bundle["model"].predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    assert acc >= MIN_ACCURACY, f"Accuracy {acc:.4f} is below minimum threshold {MIN_ACCURACY}"


def test_model_f1_above_threshold():
    bundle = get_bundle()
    _, X_test, _, y_test = get_test_split()
    y_pred = bundle["model"].predict(X_test)
    f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)
    assert f1 >= MIN_F1_MACRO, f"F1 (macro) {f1:.4f} is below minimum threshold {MIN_F1_MACRO}"


def test_model_beats_majority_class_baseline():
    _, X_test, _, y_test = get_test_split()
    bundle = get_bundle()
    y_pred = bundle["model"].predict(X_test)
    model_acc = accuracy_score(y_test, y_pred)

    majority_class = y_test.value_counts().idxmax()
    baseline_pred = [majority_class] * len(y_test)
    baseline_acc = accuracy_score(y_test, baseline_pred)

    assert model_acc > baseline_acc, (
        f"Model accuracy ({model_acc:.4f}) does not beat the majority-class "
        f"baseline ({baseline_acc:.4f}) — model may not be learning anything useful"
    )


def test_precision_recall_defined_for_all_classes():
    bundle = get_bundle()
    _, X_test, _, y_test = get_test_split()
    y_pred = bundle["model"].predict(X_test)
    precisions = precision_score(y_test, y_pred, average=None, labels=sorted(y_test.unique()), zero_division=0)
    recalls = recall_score(y_test, y_pred, average=None, labels=sorted(y_test.unique()), zero_division=0)
    assert all(p > 0 for p in precisions), "At least one class has zero precision (model never correctly predicts it)"
    assert all(r > 0 for r in recalls), "At least one class has zero recall (model never predicts it at all)"


# ===========================================================================
# LEVEL 4 — INFERENCE / INTEGRATION TESTING (predict.py)
# ===========================================================================
SAFE_FEATURES = {
    "PM01": 0, "PM02": 4, "PM03": 4, "PM04": 4, "PM05": 0,
    "AUTH01": 4, "AUTH02": 0, "AUTH03": 4, "AUTH04": 0, "AUTH05": 4,
    "PHISH01": 4, "PHISH02": 0, "PHISH03": 0, "PHISH04": 4, "PHISH05": 4,
    "SOC01": 0, "SOC02": 0, "SOC03": 4, "SOC04": 0, "SOC05": 0,
    "password_length": 16, "estimated_entropy": 78.2,
    "has_uppercase": True, "has_lowercase": True, "has_number": True, "has_symbol": True,
    "common_pattern_detected": False, "repeated_characters": False,
}

RISKY_FEATURES = {
    "PM01": 4, "PM02": 0, "PM03": 0, "PM04": 1, "PM05": 1,
    "AUTH01": 0, "AUTH02": 4, "AUTH03": 0, "AUTH04": 4, "AUTH05": 0,
    "PHISH01": 0, "PHISH02": 4, "PHISH03": 4, "PHISH04": 0, "PHISH05": 0,
    "SOC01": 4, "SOC02": 4, "SOC03": 0, "SOC04": 4, "SOC05": 4,
    "password_length": 6, "estimated_entropy": 14.5,
    "has_uppercase": False, "has_lowercase": True, "has_number": True, "has_symbol": False,
    "common_pattern_detected": True, "repeated_characters": True,
}


def test_find_best_model_locates_file():
    found = find_best_model(str(MODEL_PATH))
    assert found == MODEL_PATH.resolve()


def test_find_best_model_raises_when_missing():
    try:
        find_best_model("/definitely/does/not/exist/best_model.pkl")
        assert False, "Expected FileNotFoundError, none was raised"
    except FileNotFoundError:
        pass


def test_predict_happy_path_returns_valid_shape():
    result = predict_risk(SAFE_FEATURES, model_path=str(MODEL_PATH))
    assert result["risk_class"] in ("Low", "Moderate", "High")
    assert set(result["probabilities"].keys()) == {"Low", "Moderate", "High"}
    total_prob = sum(result["probabilities"].values())
    assert abs(total_prob - 1.0) < 0.01, f"Probabilities sum to {total_prob}, expected ~1.0"


def test_predict_missing_feature_raises_value_error():
    incomplete = {"PM01": 0}
    try:
        predict_risk(incomplete, model_path=str(MODEL_PATH))
        assert False, "Expected ValueError, none was raised"
    except ValueError as e:
        assert "Missing" in str(e)


def test_predict_bad_model_path_raises_file_not_found():
    try:
        predict_risk(SAFE_FEATURES, model_path="/nonexistent/best_model.pkl")
        assert False, "Expected FileNotFoundError, none was raised"
    except FileNotFoundError:
        pass


def test_predict_safe_profile_is_not_high_risk():
    result = predict_risk(SAFE_FEATURES, model_path=str(MODEL_PATH))
    assert result["risk_class"] != "High", (
        "A profile with entirely protective answers and a strong password "
        "was classified as High risk"
    )


def test_predict_risky_profile_is_not_low_risk():
    result = predict_risk(RISKY_FEATURES, model_path=str(MODEL_PATH))
    assert result["risk_class"] != "Low", (
        "A profile with entirely risky answers and a weak password was "
        "classified as Low risk"
    )


def test_predict_agrees_with_rubric_on_sample_of_real_rows(sample_size=20, min_agreement=0.8):
    """Consistency check: on real dataset rows, does the model's prediction
    usually match the rubric's own risk_level for that row? This directly
    tests the core claim that the model reproduces the evidence-based rubric."""
    df = get_df()
    bundle = get_bundle()
    cols = bundle["feature_columns"]

    sample = df.sample(sample_size, random_state=1)
    agree = 0
    for _, row in sample.iterrows():
        features = {c: row[c] for c in cols}
        result = predict_risk(features, model_path=str(MODEL_PATH))
        if result["risk_class"] == row["risk_level"]:
            agree += 1

    agreement_rate = agree / sample_size
    assert agreement_rate >= min_agreement, (
        f"Model only agreed with rubric labels on {agreement_rate:.0%} of "
        f"{sample_size} sampled rows (expected >= {min_agreement:.0%})"
    )


# ===========================================================================
# Fallback runner (executes all test_* functions without pytest installed)
# ===========================================================================
if __name__ == "__main__":
    import traceback

    tests = [(name, obj) for name, obj in list(globals().items())
              if name.startswith("test_") and callable(obj)]

    passed, failed = 0, 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}\n      {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {name}\n      {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
    sys.exit(1 if failed else 0)
