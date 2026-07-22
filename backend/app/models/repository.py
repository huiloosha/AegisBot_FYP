"""
Assessment repository -- all the SQL for saving and reading assessments.

Kept separate from the routes so the HTTP layer stays thin and this logic is
unit-testable without a running server. Every function takes an open sqlite3
connection (from db.get_db()) and does NOT commit -- the caller controls the
transaction boundary, so a whole assessment saves atomically or not at all.
"""
import json
import sqlite3
from datetime import datetime, timezone

from app.models.db import question_id_map


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------
def save_full_assessment(db: sqlite3.Connection, *,
                         answers: dict,
                         analyze_result: dict,
                         user_id: int | None = None,
                         consent_given: bool = False,
                         started_at: str | None = None) -> int:
    """Persist one complete assessment and all its child rows.

    answers:         {question_code: 0-4}
    analyze_result:  the dict returned by PredictorService.analyze_and_predict,
                     i.e. it has keys: risk_class, probabilities, model_used,
                     password_features, recommendations_plan.
    Returns the new assessment_id.

    The caller is responsible for db.commit() (see the route). This function
    performs many INSERTs; wrapping them in the caller's transaction means a
    failure half-way rolls the whole thing back.
    """
    now = _utcnow()
    started = started_at or now

    # 1. assessments row
    cur = db.execute(
        """
        INSERT INTO assessments
            (user_id, assessment_type, status, consent_given, started_at, completed_at)
        VALUES (?, 'full', 'completed', ?, ?, ?)
        """,
        (user_id, 1 if consent_given else 0, started, now),
    )
    assessment_id = cur.lastrowid

    # 2. behaviour_responses (20 rows). We look up question_id by code and store
    #    the per-question risk_value from the recommendations plan when available.
    qid_by_code = question_id_map(db)

    # Build a code -> contribution map from all_issues so we can persist
    # risk_value per answered question (0 for perfectly-safe answers not listed).
    plan = analyze_result.get("recommendations_plan", {})
    contrib_by_code = {
        i["code"]: i.get("contribution")
        for i in plan.get("all_issues", [])
    }

    resp_rows = []
    for code, val in answers.items():
        qid = qid_by_code.get(code)
        if qid is None:
            continue  # unknown code -> skip rather than break the whole save
        resp_rows.append((assessment_id, qid, int(val),
                          contrib_by_code.get(code)))
    db.executemany(
        """
        INSERT INTO behaviour_responses
            (assessment_id, question_id, answer_value, risk_value)
        VALUES (?, ?, ?, ?)
        """,
        resp_rows,
    )

    # 3. password_analysis (derived features only; never the raw password)
    pw = analyze_result.get("password_features", {})
    db.execute(
        """
        INSERT INTO password_analysis
            (assessment_id, password_length, estimated_entropy,
             has_uppercase, has_lowercase, has_number, has_symbol,
             common_pattern_detected, repeated_characters, password_score, analysed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assessment_id,
            pw.get("password_length"),
            pw.get("estimated_entropy"),
            int(bool(pw.get("has_uppercase"))),
            int(bool(pw.get("has_lowercase"))),
            int(bool(pw.get("has_number"))),
            int(bool(pw.get("has_symbol"))),
            int(bool(pw.get("common_pattern_detected"))),
            int(bool(pw.get("repeated_characters"))),
            analyze_result.get("password_score"),
            now,
        ),
    )

    # 4. risk_predictions (model output). risk_score = probability of the
    #    predicted class; the full probability map is stored as JSON in scores.
    risk_class = analyze_result.get("risk_class")
    probs = analyze_result.get("probabilities", {})
    risk_score = probs.get(risk_class)
    db.execute(
        """
        INSERT INTO risk_predictions
            (assessment_id, risk_score, risk_level, behaviour_score,
             password_score, scores, model_used, predicted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assessment_id,
            risk_score,
            risk_class,
            analyze_result.get("behaviour_score"),
            analyze_result.get("password_score"),
            json.dumps(probs),
            analyze_result.get("model_used"),
            now,
        ),
    )

    # 5. recommendations (the full sorted plan; completed defaults to 0)
    reco_rows = []
    for rank, item in enumerate(plan.get("all_issues", []), start=1):
        reco_rows.append((
            assessment_id,
            item.get("code"),
            item.get("category"),
            item.get("priority"),
            item.get("issue"),
            item.get("action"),
            item.get("evidence"),
            item.get("contribution"),
            rank,
        ))
    db.executemany(
        """
        INSERT INTO recommendations
            (assessment_id, code, category, priority, title, action,
             evidence, contribution, rank_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        reco_rows,
    )

    return assessment_id


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def list_assessments(db: sqlite3.Connection, user_id: int | None = None,
                     limit: int = 50) -> list[dict]:
    """Return a compact history list for a dashboard: newest first.

    Each row: assessment_id, completed_at, risk_level, risk_score,
    n_recommendations. If user_id is given, filter to that user; otherwise
    return all (useful for the anonymous/single-user prototype).
    """
    params = []
    where = ""
    if user_id is not None:
        where = "WHERE a.user_id = ?"
        params.append(user_id)

    sql = f"""
        SELECT a.assessment_id,
               a.completed_at,
               p.risk_level,
               p.risk_score,
               p.behaviour_score,
               p.password_score,
               (SELECT COUNT(*) FROM recommendations r
                 WHERE r.assessment_id = a.assessment_id) AS n_recommendations
        FROM assessments a
        LEFT JOIN risk_predictions p ON p.assessment_id = a.assessment_id
        {where}
        ORDER BY a.completed_at DESC
        LIMIT ?
    """
    params.append(limit)
    cur = db.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def get_assessment(db: sqlite3.Connection, assessment_id: int) -> dict | None:
    """Return the full detail for one assessment, reassembled into the same
    shape the /api/analyze response uses, plus stored metadata. Returns None if
    the assessment doesn't exist.
    """
    a = db.execute(
        "SELECT * FROM assessments WHERE assessment_id = ?", (assessment_id,)
    ).fetchone()
    if a is None:
        return None

    pred = db.execute(
        "SELECT * FROM risk_predictions WHERE assessment_id = ?", (assessment_id,)
    ).fetchone()

    pw = db.execute(
        "SELECT * FROM password_analysis WHERE assessment_id = ?", (assessment_id,)
    ).fetchone()

    responses = db.execute(
        """
        SELECT q.question_code, br.answer_value, br.risk_value
        FROM behaviour_responses br
        JOIN questions q ON q.question_id = br.question_id
        WHERE br.assessment_id = ?
        ORDER BY q.display_order
        """,
        (assessment_id,),
    ).fetchall()

    recos = db.execute(
        """
        SELECT recommend_id, code, category, priority, title AS issue, action,
               evidence, contribution, rank_order, completed
        FROM recommendations
        WHERE assessment_id = ?
        ORDER BY rank_order
        """,
        (assessment_id,),
    ).fetchall()

    return {
        "assessment_id": a["assessment_id"],
        "user_id": a["user_id"],
        "status": a["status"],
        "consent_given": bool(a["consent_given"]),
        "started_at": a["started_at"],
        "completed_at": a["completed_at"],
        "risk_class": pred["risk_level"] if pred else None,
        "risk_score": pred["risk_score"] if pred else None,
        "probabilities": json.loads(pred["scores"]) if pred and pred["scores"] else {},
        "model_used": pred["model_used"] if pred else None,
        "password_features": {
            k: pw[k] for k in (
                "password_length", "estimated_entropy", "has_uppercase",
                "has_lowercase", "has_number", "has_symbol",
                "common_pattern_detected", "repeated_characters",
            )
        } if pw else {},
        "behaviour_score": pred["behaviour_score"] if pred else None,
        "password_score": pw["password_score"] if pw else None,
        "answers": {r["question_code"]: r["answer_value"] for r in responses},
        "recommendations": [dict(r) for r in recos],
        "recommendations_plan": {
            "recommendations": [dict(r) for r in recos[:5]],
            "all_issues": [dict(r) for r in recos],
        },
    }


def set_recommendation_completed(db: sqlite3.Connection, recommend_id: int,
                                 completed: bool) -> bool:
    """Mark a single recommendation done/undone (for progress tracking).
    Returns True if a row was updated."""
    cur = db.execute(
        "UPDATE recommendations SET completed = ? WHERE recommend_id = ?",
        (1 if completed else 0, recommend_id),
    )
    return cur.rowcount > 0


def list_questions(db: sqlite3.Connection) -> list[dict]:
    """Return all questions ordered by display_order, for building the form.

    Public data (no user scoping): the frontend fetches these once to render the
    assessment form, so both guests and registered users need them. Ordered by
    display_order so the questions appear grouped by category, the same order as
    in rubric.py.
    """
    cur = db.execute(
        """
        SELECT question_id, question_code, question_text, explanation,
               category, response_type, risk_direction, display_order
        FROM questions
        ORDER BY display_order
        """
    )
    # sqlite3.Row -> plain dict so Flask's jsonify can serialize it.
    return [dict(r) for r in cur.fetchall()]
