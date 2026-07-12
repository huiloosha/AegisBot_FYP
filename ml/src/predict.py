# -*- coding: utf-8 -*-
"""
AegisBot — Inference Script (predict.py)

Loads best_model.pkl (produced by train.py), validates a user's raw feature
dict against the model's expected 28 features, orders them correctly, and
returns the predicted risk_level plus class probabilities.

Usage as a script:
    python predict.py --input user_features.json
    python predict.py --input user_features.json --model ../models/best_model.pkl
    python predict.py --example                      # print a fill-in-the-blanks template

Usage as a module (e.g. from the Flask backend):
    from predict import predict_risk
    result = predict_risk(features_dict)
    # result = {"risk_class": "Moderate",
    #           "probabilities": {"Low": 0.12, "Moderate": 0.71, "High": 0.17},
    #           "model_used": "SVM (RBF)"}
"""
import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Locate best_model.pkl
# ---------------------------------------------------------------------------
DEFAULT_SEARCH_PATHS = [
    Path(__file__).resolve().parent / "best_model.pkl",
    Path(__file__).resolve().parent.parent / "models" / "best_model.pkl",
    Path.cwd() / "best_model.pkl",
    Path.cwd() / "ml" / "models" / "best_model.pkl",
]


def find_best_model(explicit_path: str | None = None) -> Path:
    """Find best_model.pkl: use explicit_path if given, otherwise search the
    default locations. Raises FileNotFoundError with a clear message if
    nothing is found."""
    if explicit_path:
        p = Path(explicit_path).resolve()
        if not p.is_file():
            raise FileNotFoundError(
                f"best_model.pkl not found at explicitly given path: {p}"
            )
        return p

    for p in DEFAULT_SEARCH_PATHS:
        if p.is_file():
            return p.resolve()

    searched = "\n  - ".join(str(p) for p in DEFAULT_SEARCH_PATHS)
    raise FileNotFoundError(
        "Could not find best_model.pkl in any default location. "
        f"Searched:\n  - {searched}\n"
        "Run train.py first, or pass --model /path/to/best_model.pkl explicitly."
    )


# ---------------------------------------------------------------------------
# 2. Load the saved model bundle
# ---------------------------------------------------------------------------
def load_bundle(model_path: Path) -> dict:
    bundle = joblib.load(model_path)
    required_keys = {"model", "model_name", "feature_columns", "classes"}
    missing = required_keys - set(bundle.keys())
    if missing:
        raise ValueError(
            f"best_model.pkl at {model_path} is missing expected metadata keys: "
            f"{sorted(missing)}. Was it saved by train.py?"
        )
    return bundle


# ---------------------------------------------------------------------------
# 3-4. Validate the user's raw feature dict against the model's expected features
# ---------------------------------------------------------------------------
def validate_features(features: dict, required_columns: list[str]) -> None:
    """Raises ValueError listing exactly what's missing (and, as a courtesy,
    what's unexpected/extra) if the input doesn't match the model's schema."""
    provided = set(features.keys())
    required = set(required_columns)

    missing = required - provided
    if missing:
        raise ValueError(
            f"Missing {len(missing)} required feature(s): {sorted(missing)}. "
            f"The model expects exactly these {len(required_columns)} features: "
            f"{required_columns}"
        )

    extra = provided - required
    if extra:
        print(f"[predict.py] Note: ignoring {len(extra)} unexpected field(s) not "
              f"used by the model: {sorted(extra)}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 5. Order the features exactly as the model expects
# ---------------------------------------------------------------------------
def build_feature_row(features: dict, required_columns: list[str]) -> pd.DataFrame:
    row = {}
    for col in required_columns:
        val = features[col]
        if isinstance(val, bool):
            val = int(val)
        row[col] = val
    # single-row DataFrame, columns in the exact order the model was trained on
    return pd.DataFrame([row], columns=required_columns)


# ---------------------------------------------------------------------------
# 6-7. Predict risk class + probabilities
# ---------------------------------------------------------------------------
def predict_risk(features: dict, model_path: str | None = None) -> dict:
    """
    features: flat dict of the user's 28 raw inputs (question codes ->
              0-4 ordinal answers, plus password_length, estimated_entropy,
              has_uppercase, has_lowercase, has_number, has_symbol,
              common_pattern_detected, repeated_characters).
    Returns: {"risk_class": str, "probabilities": {class: float, ...},
              "model_used": str}
    """
    path = find_best_model(model_path)
    bundle = load_bundle(path)

    model = bundle["model"]
    feature_columns = bundle["feature_columns"]
    classes = bundle["classes"]

    validate_features(features, feature_columns)
    X_row = build_feature_row(features, feature_columns)

    pred_class = model.predict(X_row)[0]

    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X_row)[0]
        model_classes = list(model.classes_)
        probabilities = {cls: round(float(p), 4) for cls, p in zip(model_classes, proba)}
        # ensure every known class is present (0.0 if model never predicts it)
        for cls in classes:
            probabilities.setdefault(cls, 0.0)
    else:
        # fallback: hard prediction only, no calibrated probabilities available
        probabilities = {cls: (1.0 if cls == pred_class else 0.0) for cls in classes}

    return {
        "risk_class": pred_class,
        "probabilities": probabilities,
        "model_used": bundle["model_name"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def print_example_template(model_path: str | None = None):
    """Prints a fill-in-the-blanks JSON template with the exact 28 keys the
    currently saved model expects, in order."""
    path = find_best_model(model_path)
    bundle = load_bundle(path)
    template = {col: "<fill in>" for col in bundle["feature_columns"]}
    print(json.dumps(template, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Run inference with AegisBot's best_model.pkl.")
    parser.add_argument("--input", type=str, help="Path to a JSON file with the user's 28 raw features.")
    parser.add_argument("--model", type=str, default=None,
                         help="Path to best_model.pkl (optional; auto-detected by default).")
    parser.add_argument("--example", action="store_true",
                         help="Print a fill-in-the-blanks JSON template and exit.")
    args = parser.parse_args()

    if args.example:
        print_example_template(args.model)
        return

    if not args.input:
        parser.error("--input is required unless --example is given.")

    with open(args.input) as f:
        features = json.load(f)

    try:
        result = predict_risk(features, args.model)
    except (FileNotFoundError, ValueError) as e:
        print(f"[predict.py] Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
