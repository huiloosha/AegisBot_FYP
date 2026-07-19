"""
Predictor service — the bridge between the Flask API and the ML code.

Why this file exists:
  - Your prediction logic already lives in ml/src/predict.py (predict_risk).
    We do NOT reimplement it here — that would create two sources of truth.
    Instead we import it and call it. The ML team owns the model; the backend
    just exposes it over HTTP.
  - The model pickle is loaded ONCE, when the app starts, not on every request.
    Unpickling an SVM + scaler on every /api/predict call would be slow and
    wasteful. We warm it up at startup and reuse it.

How the import works:
  ml/src/ is outside docs/backend/, so Python can't see predict.py by default.
  We compute the path to ml/src/ and add it to sys.path, then import predict_risk.
"""
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Locate ml/src/ relative to THIS file and make predict.py importable.
#    this file: <root>/docs/backend/app/services/predictor.py
#    ml/src:    <root>/ml/src
#    So we go up 4 parents (services -> app -> backend -> docs -> <root>).
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ML_SRC = _PROJECT_ROOT / "ml" / "src"

if str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))

# Now this import resolves to ml/src/predict.py
from predict import predict_risk, find_best_model, load_bundle
from password_analysis import analyze_password, password_strength_score
from recommender import build_recommendations
from rubric import behaviour_risk_and_score


class PredictorService:
    """Holds the loaded model bundle and answers prediction requests.

    We keep the loaded bundle metadata (feature list, classes, model name) so
    the API can report what it expects and which model is serving — handy for
    the frontend and for your /api/health-style diagnostics.
    """

    def __init__(self, model_path: str | None = None):
        # Resolve and load the bundle once, here at construction time.
        self._model_path = find_best_model(model_path)
        bundle = load_bundle(self._model_path)

        self.model_name = bundle["model_name"]
        self.feature_columns = list(bundle["feature_columns"])
        self.classes = list(bundle["classes"])

    def predict(self, features: dict) -> dict:
        """Delegate to the ML module's predict_risk.

        predict_risk raises ValueError if the feature dict is missing required
        keys — we let that propagate so the route can turn it into an HTTP 400.
        Returns: {"risk_class", "probabilities", "model_used"}.
        """
        return predict_risk(features, str(self._model_path))
    
    def analyze_and_predict(self, password: str, answers: dict) -> dict:
        """Analyze the raw password, combine it with behavioural answers,
        run the ML prediction, calculate the final score, and generate
        personalized recommendations.
        """

        # 1. Analyze the raw password
        pw_features = analyze_password(password)

        # 2. Merge 20 behavioural answers with 8 password features
        features = {**answers, **pw_features}

        # 3. Get the original ML prediction
        result = predict_risk(features, str(self._model_path))

        # 4. Calculate separate password and behaviour scores
        password_score = password_strength_score(pw_features)

        _, behaviour_score = behaviour_risk_and_score(answers)

        result["password_score"] = password_score
        result["behaviour_score"] = behaviour_score

        # 5. Calculate the combined security score
        final_score = round(
            behaviour_score * 0.65
            + password_score * 0.35
        )

        # 6. Determine the final risk level
        # A critically weak password can never result in Low Risk.
        if password_score < 20:
            final_risk = "High"

        elif password_score < 40:
            if final_score >= 70:
                final_risk = "Moderate"
            else:
                final_risk = "High"

        else:
            if final_score >= 80:
                final_risk = "Low"
            elif final_score >= 55:
                final_risk = "Moderate"
            else:
                final_risk = "High"

        # 7. Store both the original ML result and the adjusted final result
        result["ml_risk_class"] = result.get("risk_class")
        result["overall_score"] = final_score
        result["risk_class"] = final_risk

        # 8. Generate personalized recommendations
        result["recommendations_plan"] = build_recommendations(
            answers,
            pw_features,
            final_risk,
        )

        # Optional: return derived password features for the frontend
        result["password_features"] = pw_features

        return result

    def info(self) -> dict:
        """Small summary the API can expose (what the model expects/serves)."""
        return {
            "model_used": self.model_name,
            "model_path": str(self._model_path),
            "n_features": len(self.feature_columns),
            "feature_columns": self.feature_columns,
            "classes": self.classes,
        }


# ---------------------------------------------------------------------------
# 2. Module-level singleton, created lazily.
#    get_predictor() builds the service on first call and reuses it after,
#    so the model is loaded exactly once per process.
# ---------------------------------------------------------------------------
_predictor: PredictorService | None = None


def get_predictor() -> PredictorService:
    global _predictor
    if _predictor is None:
        _predictor = PredictorService()
    return _predictor