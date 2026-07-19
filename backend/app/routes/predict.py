"""
Prediction endpoint.

POST /api/predict
  Body: JSON object with the 28 raw features (see /api/predict/schema).
  Success -> 200 with {"risk_class", "probabilities", "model_used"}.
  Bad input (missing/extra features, not JSON) -> 400 with an "error" message.

GET /api/predict/schema
  Returns the exact features the model expects, so the frontend can build the
  form and validate before sending.

Design notes:
  - The route is thin. All ML logic lives in the service, which itself defers
    to ml/src/predict.py. The route's job is HTTP: parse, call, shape response.
  - predict_risk raises ValueError on invalid features. We catch it and return
    400 (client's fault), not 500 (server's fault). Unexpected errors become 500.
"""
from flask import Blueprint, jsonify, request

from app.services.predictor import get_predictor

predict_bp = Blueprint("predict", __name__, url_prefix="/api")


@predict_bp.route("/predict", methods=["POST"])
def predict():
    # 1. Require a JSON body. force=False means a wrong Content-Type is rejected.
    #    silent=True makes Flask return None instead of raising, so we control
    #    the error message.
    features = request.get_json(silent=True)
    if features is None:
        return jsonify({
            "error": "Request body must be JSON. Set Content-Type: application/json."
        }), 400

    if not isinstance(features, dict):
        return jsonify({
            "error": "JSON body must be an object mapping feature names to values."
        }), 400

    # 2. Delegate to the service. ValueError = bad input from the client (400).
    try:
        result = get_predictor().predict(features)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError as e:
        # Model file missing = server misconfiguration, not the client's fault.
        return jsonify({"error": f"Model not available: {e}"}), 500

    # 3. Success.
    return jsonify(result), 200


@predict_bp.route("/analyze", methods=["POST"])
def analyze():
    """Frontend-friendly endpoint: send a raw password + the 20 answers, get a
    prediction back (the 8 password features are computed server-side).

    Body: {"password": "<string>", "answers": {"PM01": 0, ..., "SOC05": 3}}
    Success -> 200 with {"risk_class", "probabilities", "model_used",
                         "password_features"}.
    """
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        return jsonify({
            "error": "Request body must be a JSON object with 'password' and 'answers'."
        }), 400

    password = body.get("password")
    answers = body.get("answers")

    if not isinstance(password, str) or password == "":
        return jsonify({"error": "'password' must be a non-empty string."}), 400
    if not isinstance(answers, dict):
        return jsonify({"error": "'answers' must be an object of question codes to 0-4 values."}), 400

    try:
        result = get_predictor().analyze_and_predict(password, answers)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"error": f"Model not available: {e}"}), 500

    return jsonify(result), 200


@predict_bp.route("/predict/schema", methods=["GET"])
def schema():
    """Expose what the model expects so the frontend can build/validate the form."""
    return jsonify(get_predictor().info()), 200


@predict_bp.route("/password-check", methods=["POST"])
def password_check():
    """Standalone password strength check (no behavioural questions).

    Body: {"password": "<string>"}
    Success -> 200 with {"password_features", "password_score"}.
    The raw password is analysed for its features and discarded; it is never
    stored or used for authentication.
    """
    import sys
    from pathlib import Path
    # ml/src is already on sys.path via the predictor service import, but ensure it
    ml_src = Path(__file__).resolve().parents[3] / "ml" / "src"
    if str(ml_src) not in sys.path:
        sys.path.insert(0, str(ml_src))
    from password_analysis import analyze_password, password_strength_score

    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object with 'password'."}), 400

    password = body.get("password")
    if not isinstance(password, str) or password == "":
        return jsonify({"error": "'password' must be a non-empty string."}), 400

    features = analyze_password(password)
    score = password_strength_score(features)
    return jsonify({
        "password_features": features,
        "password_score": score,
    }), 200