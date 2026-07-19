-- AegisBot -- SQLite schema
-- Mirrors the project ERD. One database file, seven tables.
--
-- Design choices worth noting:
--  * We NEVER store the raw assessed password. Only the 8 derived features
--    live in password_analysis. The users.password_hash column is for account
--    login only (a bcrypt/argon2 hash), never the assessment password.
--  * All timestamps are ISO-8601 UTC strings written by the app layer.
--  * Foreign keys use ON DELETE CASCADE so deleting an assessment cleans up its
--    child rows (responses, analysis, prediction, recommendations) in one go.
--    (SQLite enforces this only when PRAGMA foreign_keys = ON, which db.py sets
--    on every connection.)

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT,                       -- account login hash; NOT the assessed password
    created_at    TEXT    NOT NULL            -- ISO-8601 UTC
);

-- ---------------------------------------------------------------------------
-- Questions  (reference/lookup table, seeded from rubric.py)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS questions (
    question_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    question_code  TEXT    NOT NULL UNIQUE,   -- PM01, AUTH01, ...
    question_text  TEXT    NOT NULL,
    explanation    TEXT,                       -- the rubric "evidence" string
    category       TEXT    NOT NULL,           -- PM / AUTH / PHISH / SOC
    response_type  TEXT    NOT NULL,           -- scale / frequency / yes_no
    risk_direction TEXT    NOT NULL,           -- direct / reverse
    display_order  INTEGER NOT NULL
);

-- ---------------------------------------------------------------------------
-- Assessments  (one row per completed assessment run)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assessments (
    assessment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,                   -- nullable: anonymous assessments allowed
    assessment_type TEXT    NOT NULL DEFAULT 'full',
    status          TEXT    NOT NULL DEFAULT 'completed',  -- in_progress / completed
    consent_given   INTEGER NOT NULL DEFAULT 0,            -- 0/1 boolean
    started_at      TEXT    NOT NULL,
    completed_at    TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------------
-- Behaviour_Responses  (20 rows per assessment: one per question)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS behaviour_responses (
    response_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL,
    question_id   INTEGER NOT NULL,
    answer_value  INTEGER NOT NULL,            -- 0-4 raw ordinal
    risk_value    REAL,                        -- risk_fraction * weight * cat_weight * 100
    FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id) ON DELETE CASCADE,
    FOREIGN KEY (question_id)   REFERENCES questions(question_id)
);

-- ---------------------------------------------------------------------------
-- Password_Analysis  (one row per assessment; derived features only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_analysis (
    pwdanalysis_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id           INTEGER NOT NULL UNIQUE,   -- one-to-one with assessment
    password_length         INTEGER,
    estimated_entropy       REAL,
    has_uppercase           INTEGER,
    has_lowercase           INTEGER,
    has_number              INTEGER,
    has_symbol              INTEGER,
    common_pattern_detected INTEGER,
    repeated_characters     INTEGER,
    password_score          REAL,               -- 0-100 strength (optional, computed)
    analysed_at             TEXT NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Risk_Predictions  (one row per assessment: the model output)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL UNIQUE,          -- one-to-one with assessment
    risk_score    REAL,                          -- e.g. probability of the predicted class
    risk_level    TEXT    NOT NULL,              -- Low / Moderate / High
    behaviour_score REAL,                        -- 0-100 objective behaviour score (higher = safer)
    password_score  REAL,                        -- 0-100 objective password score (higher = safer)
    scores        TEXT,                          -- JSON blob: full class-probability map
    model_used    TEXT,
    predicted_at  TEXT    NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Recommendations  (N rows per assessment: the personalized plan)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recommendations (
    recommend_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL,
    code          TEXT,                          -- PM01, PW_SHORT, ...
    category      TEXT,
    priority      TEXT,                          -- high / medium / low
    title         TEXT,                          -- the "issue" text
    action        TEXT,                          -- the corrective action
    evidence      TEXT,
    contribution  REAL,
    rank_order    INTEGER,                       -- position in the sorted plan
    completed     INTEGER NOT NULL DEFAULT 0,    -- 0/1: user has actioned it
    FOREIGN KEY (assessment_id) REFERENCES assessments(assessment_id) ON DELETE CASCADE
);

-- Helpful indexes for the dashboard/history queries.
CREATE INDEX IF NOT EXISTS idx_assessments_user      ON assessments(user_id);
CREATE INDEX IF NOT EXISTS idx_responses_assessment  ON behaviour_responses(assessment_id);
CREATE INDEX IF NOT EXISTS idx_predictions_assessment ON risk_predictions(assessment_id);
CREATE INDEX IF NOT EXISTS idx_reco_assessment       ON recommendations(assessment_id);

-- ---------------------------------------------------------------------------
-- Sessions  (bearer tokens issued at login)
-- ---------------------------------------------------------------------------
-- A minimal token-session store. On login we insert a random token here; each
-- authenticated request presents it and we resolve it back to a user_id. On
-- logout we delete the row. Tokens carry an expiry so stale ones can be
-- rejected/cleaned up.
--
-- PROTOTYPE NOTE: storing opaque tokens server-side (rather than signed JWTs)
-- is a deliberate simplicity choice for the FYP -- easy to reason about and to
-- revoke. A production system might use signed, stateless tokens and rotate a
-- signing secret.
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT    PRIMARY KEY,          -- random opaque bearer token
    user_id    INTEGER NOT NULL,
    created_at TEXT    NOT NULL,
    expires_at TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
