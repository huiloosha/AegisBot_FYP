"""
Assessment persistence & retrieval endpoints.

  GET  /api/questions
      Returns the 20 assessment questions (public; used to build the form).

  POST /api/assessments
      Body: {"password": "...", "answers": {...}, "consent_given": bool,
             "user_id": int|null}
      Runs analysis AND saves it. Returns the analysis result plus the new
      assessment_id. This is the "analyze and remember" path.

  GET  /api/assessments
      Query: ?user_id=<int> (optional), ?limit=<int> (default 50)
      Returns a compact history list (newest first) for a dashboard.

  GET  /api/assessments/<assessment_id>
      Returns the full stored detail of one assessment (previous result view).

  PATCH /api/recommendations/<recommend_id>
      Body: {"completed": bool}
      Marks one recommendation done/undone (progress tracking).

The plain /api/analyze route (in predict.py) is left as a stateless "analyze
without saving" option, so nothing that already calls it breaks.
"""
from flask import Blueprint, jsonify, request

from app.models.db import get_db
from app.models import repository as repo
from app.routes.auth_helpers import current_user_id
from app.services.predictor import get_predictor

assessments_bp = Blueprint("assessments", __name__, url_prefix="/api")


@assessments_bp.route("/questions", methods=["GET"])
def list_questions():
    """Serve the 20 assessment questions so the frontend can build the form.

    Public (no auth): guests take the assessment too, so they need the questions.
    """
    db = get_db()                       # per-request DB connection
    questions = repo.list_questions(db) # read all questions, ordered
    return jsonify({
        "questions": questions,
        "count": len(questions),
    }), 200


@assessments_bp.route("/assessments", methods=["POST"])
def create_assessment():
    body = request.get_json(silent=True)
    if body is None or not isinstance(body, dict):
        return jsonify({
            "error": "Request body must be a JSON object with 'password' and 'answers'."
        }), 400

    password = body.get("password")
    answers = body.get("answers")
    consent_given = bool(body.get("consent_given", False))

    # user_id comes from the authenticated session token (Authorization header),
    # NOT from the request body. An anonymous request (no/invalid token) resolves
    # to None -> guest path. This prevents a caller from saving into someone
    # else's history by putting their id in the body.
    user_id = current_user_id()

    if not isinstance(password, str) or password == "":
        return jsonify({"error": "'password' must be a non-empty string."}), 400
    if not isinstance(answers, dict):
        return jsonify({"error": "'answers' must be an object of question codes to 0-4 values."}), 400

    # 1. Analyze (same path /api/analyze uses). This runs for everyone --
    #    guest or registered -- because the result is always returned.
    try:
        result = get_predictor().analyze_and_predict(password, answers)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"error": f"Model not available: {e}"}), 500

    # 2. Guest vs. registered fork.
    #    No token / invalid token -> guest: analyze and return, but DO NOT
    #                   persist. Nothing is stored, so there is no history and no
    #                   personal data at rest.
    #    Valid token             -> registered: persist the assessment, linked to
    #                   the authenticated user, so it shows up in their history.
    if user_id is None:
        result["saved"] = False
        result["assessment_id"] = None
        return jsonify(result), 200

    # 3. Consent is required to PERSIST a full assessment (we are about to store
    #    the user's answers and derived password analysis against their account).
    #    The guest path above needs no consent because nothing is stored.
    if not consent_given:
        return jsonify({
            "error": "Consent is required to save the assessment. "
                     "Set 'consent_given': true, or omit authentication to run "
                     "a guest assessment that is not stored."
        }), 400

    # 4. Registered user: the user must exist (FK integrity). Check explicitly so
    #    we can return a clear 404 rather than a generic 500 from the FK failure.
    db = get_db()
    user_row = db.execute(
        "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    if user_row is None:
        return jsonify({
            "error": f"No user with user_id={user_id}. Register or log in first."
        }), 404

    # Persist atomically. The repository doesn't commit; we do it here so the
    # whole assessment saves or none of it does.
    try:
        assessment_id = repo.save_full_assessment(
            db,
            answers=answers,
            analyze_result=result,
            user_id=user_id,
            consent_given=consent_given,
        )
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return jsonify({"error": f"Failed to save assessment: {e}"}), 500

    result["saved"] = True
    result["assessment_id"] = assessment_id
    return jsonify(result), 201


@assessments_bp.route("/assessments", methods=["GET"])
def list_history():
    # History is private: only the authenticated user's own assessments. This
    # ignores any ?user_id in the query and uses the token instead, so users
    # cannot read each other's history.
    user_id = current_user_id()
    if user_id is None:
        return jsonify({"error": "Authentication required to view history."}), 401
    limit = request.args.get("limit", default=50, type=int)
    db = get_db()
    items = repo.list_assessments(db, user_id=user_id, limit=limit)
    return jsonify({"assessments": items, "count": len(items)}), 200


@assessments_bp.route("/assessments/<int:assessment_id>", methods=["GET"])
def get_one(assessment_id: int):
    # An assessment's detail is only viewable by the user who owns it.
    user_id = current_user_id()
    if user_id is None:
        return jsonify({"error": "Authentication required."}), 401
    db = get_db()
    detail = repo.get_assessment(db, assessment_id)
    if detail is None:
        return jsonify({"error": f"Assessment {assessment_id} not found."}), 404
    if detail.get("user_id") != user_id:
        # Don't reveal existence of other users' assessments -> 404, not 403.
        return jsonify({"error": f"Assessment {assessment_id} not found."}), 404
    return jsonify(detail), 200


@assessments_bp.route("/recommendations/<int:recommend_id>", methods=["PATCH"])
def update_recommendation(recommend_id: int):
    user_id = current_user_id()
    if user_id is None:
        return jsonify({"error": "Authentication required."}), 401

    body = request.get_json(silent=True)
    if body is None or "completed" not in body:
        return jsonify({"error": "Body must be a JSON object with a 'completed' boolean."}), 400

    db = get_db()
    # Ownership: the recommendation must belong to an assessment owned by this
    # user. If not (or it doesn't exist), return 404 without distinguishing.
    owner = db.execute(
        """
        SELECT a.user_id
        FROM recommendations r
        JOIN assessments a ON a.assessment_id = r.assessment_id
        WHERE r.recommend_id = ?
        """,
        (recommend_id,),
    ).fetchone()
    if owner is None or owner["user_id"] != user_id:
        return jsonify({"error": f"Recommendation {recommend_id} not found."}), 404

    ok = repo.set_recommendation_completed(db, recommend_id, bool(body["completed"]))
    if not ok:
        return jsonify({"error": f"Recommendation {recommend_id} not found."}), 404
    db.commit()
    return jsonify({"recommend_id": recommend_id, "completed": bool(body["completed"])}), 200
