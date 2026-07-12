# -*- coding: utf-8 -*-
"""
AegisBot — ML Training Pipeline (train.py)

Loads the Evidence-Based Synthetic Cyber Hygiene Dataset, splits it into
model inputs (X) and rubric-derived labels (y), trains four candidate
classifiers, compares them on Accuracy / Precision / Recall / F1-score,
and serializes the best-performing model to best_model.pkl.

NOTE ON LABELS (see docs/AegisBot_ML_Design_Tables.xlsx -> "Notes & Limitations"):
risk_level is computed deterministically from the same 28 input features via
the evidence-based scoring rubric (rubric.py). It is not an independently
verified real-world outcome. This script therefore evaluates the model's
ability to REPRODUCE the rubric-based classification, not to predict a
ground-truth external event.

Usage:
    python train.py
    python train.py --data ../data/AegisBot_Evidence-Based_Synthetic_Cyber_Hygiene_Dataset.csv --outdir ../models
"""
import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report,
                              confusion_matrix, f1_score, precision_score,
                              recall_score)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rubric import QUESTIONS  # noqa: E402

RANDOM_STATE = 42

# Feature columns (X) — must match the "Feature Table" sheet in
# docs/AegisBot_ML_Design_Tables.xlsx exactly. Category subscores /
# behaviour_score / password_score / overall_risk_score are LABEL-side
# outputs and are deliberately excluded from X to avoid leakage.
QUESTION_COLS = [q["code"] for q in QUESTIONS]
PASSWORD_NUMERIC_COLS = ["password_length", "estimated_entropy"]
PASSWORD_BOOL_COLS = ["has_uppercase", "has_lowercase", "has_number", "has_symbol",
                      "common_pattern_detected", "repeated_characters"]
FEATURE_COLS = QUESTION_COLS + PASSWORD_NUMERIC_COLS + PASSWORD_BOOL_COLS
TARGET_COL = "risk_level"


def load_data(csv_path: Path) -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(csv_path)
    missing = [c for c in FEATURE_COLS + [TARGET_COL] if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing expected columns: {missing}")

    X = df[FEATURE_COLS].copy()
    for c in PASSWORD_BOOL_COLS:
        X[c] = X[c].astype(int)

    y = df[TARGET_COL].copy()
    return X, y


def build_candidates() -> dict:
    """Each candidate is a Pipeline so scaling only ever sees training folds."""
    return {
        "Logistic Regression": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)),
        ]),
        "Decision Tree": Pipeline([
            ("clf", DecisionTreeClassifier(max_depth=8, random_state=RANDOM_STATE)),
        ]),
        "Random Forest": Pipeline([
            ("clf", RandomForestClassifier(n_estimators=300, max_depth=12,
                                            random_state=RANDOM_STATE)),
        ]),
        "SVM (RBF)": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(kernel="rbf", probability=True, random_state=RANDOM_STATE)),
        ]),
    }


def evaluate_model(name, model, X_train, X_test, y_train, y_test, cv_folds=5):
    t0 = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - t0

    y_pred = model.predict(X_test)

    cv_scores = cross_val_score(model, X_train, y_train, cv=cv_folds, scoring="f1_macro")

    metrics = {
        "model": name,
        "accuracy": accuracy_score(y_test, y_pred),
        "precision_macro": precision_score(y_test, y_pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y_test, y_pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y_test, y_pred, average="macro", zero_division=0),
        "cv_f1_macro_mean": cv_scores.mean(),
        "cv_f1_macro_std": cv_scores.std(),
        "train_time_sec": round(train_time, 3),
    }
    report = classification_report(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=sorted(y_test.unique()))
    return metrics, report, cm, y_pred


def main():
    parser = argparse.ArgumentParser(description="Train and compare AegisBot risk-classification models.")
    parser.add_argument("--data", type=str,
                         default="../data/AegisBot_Evidence-Based_Synthetic_Cyber_Risk_Dataset.csv",
                         help="Path to the dataset CSV.")
    parser.add_argument("--outdir", type=str, default="../models",
                         help="Directory to write best_model.pkl and metrics report into.")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--cv-folds", type=int, default=5)
    args = parser.parse_args()

    csv_path = Path(args.data).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] Loading dataset from: {csv_path}")
    X, y = load_data(csv_path)
    print(f"      X shape: {X.shape}   y distribution: {dict(y.value_counts())}")

    print(f"[2/5] Splitting train/test ({int((1-args.test_size)*100)}/{int(args.test_size*100)}, stratified)")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=RANDOM_STATE, stratify=y
    )
    print(f"      Train: {X_train.shape[0]} rows   Test: {X_test.shape[0]} rows")

    print("[3/5] Training candidate models: Logistic Regression, Decision Tree, "
          "Random Forest, SVM (RBF)")
    candidates = build_candidates()
    results = []
    reports = {}
    confusions = {}
    fitted_models = {}

    for name, model in candidates.items():
        print(f"      -> training {name} ...")
        metrics, report, cm, y_pred = evaluate_model(
            name, model, X_train, X_test, y_train, y_test, cv_folds=args.cv_folds
        )
        results.append(metrics)
        reports[name] = report
        confusions[name] = cm
        fitted_models[name] = model

    results_df = pd.DataFrame(results).sort_values("f1_macro", ascending=False).reset_index(drop=True)

    print("\n[4/5] Model comparison (sorted by F1-score, macro-averaged):\n")
    print(results_df.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    best_name = results_df.iloc[0]["model"]
    best_model = fitted_models[best_name]
    best_metrics = results_df.iloc[0].to_dict()

    print(f"\n[5/5] Best model: {best_name}")
    print(f"      Test Accuracy : {best_metrics['accuracy']:.4f}")
    print(f"      Precision (macro): {best_metrics['precision_macro']:.4f}")
    print(f"      Recall (macro)   : {best_metrics['recall_macro']:.4f}")
    print(f"      F1-score (macro) : {best_metrics['f1_macro']:.4f}")
    print(f"\nClassification report for {best_name}:\n{reports[best_name]}")
    print(f"Confusion matrix (labels={sorted(y_test.unique())}):\n{confusions[best_name]}")

    # ---------------------------------------------------------------
    # Save best model + metadata
    # ---------------------------------------------------------------
    model_path = outdir / "best_model.pkl"
    joblib.dump({
        "model": best_model,
        "model_name": best_name,
        "feature_columns": FEATURE_COLS,
        "target_column": TARGET_COL,
        "classes": sorted(y.unique().tolist()),
        "trained_on": str(csv_path.name),
        "random_state": RANDOM_STATE,
    }, model_path)
    print(f"\nSaved best model -> {model_path}")

    # Save comparison table + full report as JSON for the write-up / appendix
    report_path = outdir / "training_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "best_model": best_name,
            "comparison_table": results_df.to_dict(orient="records"),
            "classification_reports": reports,
            "confusion_matrices": {k: v.tolist() for k, v in confusions.items()},
            "label_caveat": (
                "risk_level is rubric-derived (deterministic function of the same "
                "28 input features), not an independently verified real-world "
                "outcome. These metrics measure the model's ability to reproduce "
                "the evidence-based scoring rubric, per docs/AegisBot_ML_Design_"
                "Tables.xlsx -> 'Notes & Limitations'."
            ),
        }, f, indent=2)
    print(f"Saved full metrics report -> {report_path}")

    results_csv_path = outdir / "model_comparison.csv"
    results_df.to_csv(results_csv_path, index=False)
    print(f"Saved comparison table -> {results_csv_path}")


if __name__ == "__main__":
    main()
