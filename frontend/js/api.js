// Where the Flask backend runs during development.
const API_BASE = "/api";
 
/* ---- Auth token storage ----
   When a user logs in, the backend returns a token. We keep it in
   localStorage so it survives page navigation and refreshes.
   (For a prototype this is fine; a production app would consider
   httpOnly cookies.) */
const TOKEN_KEY = "aegisbot_token";
 
function saveToken(token) { localStorage.setItem(TOKEN_KEY, token); }
function getToken()      { return localStorage.getItem(TOKEN_KEY); }
function clearToken()    { localStorage.removeItem(TOKEN_KEY); }
function isLoggedIn()    { return !!getToken(); }
 
/* Build headers, adding the Authorization token when we have one. */
function authHeaders(extra = {}) {
    const headers = { "Content-Type": "application/json", ...extra };
    const token = getToken();
    if (token) headers["Authorization"] = "Bearer " + token;
    return headers;
}
 
/* A thin wrapper around fetch that:
   - adds JSON + auth headers
   - parses the JSON response
   - throws an Error (with the backend's message) on non-2xx,
     so callers can try/catch and show the message. */
async function request(path, options = {}) {
    const res = await fetch(API_BASE + path, {
        ...options,
        headers: authHeaders(options.headers),
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* no body */ }
    if (!res.ok) {
        // A 401 means our token is missing/expired/invalid. Clear it so the app
        // treats the user as logged out instead of looping on a dead token.
        if (res.status === 401) clearToken();
        const msg = (data && data.error) ? data.error : `Request failed (${res.status})`;
        throw new Error(msg);
    }
    return data;
}
 
/* ---------- Endpoint functions ---------- */
 
const api = {
    // token helpers exposed for pages to use
    saveToken, getToken, clearToken, isLoggedIn,
 
    // GET /api/questions -> { questions: [...], count }
    getQuestions() {
        return request("/questions", { method: "GET" });
    },
 
    // POST /api/assessments -> analysis result (+ assessment_id if saved)
    // body: { password, answers, consent_given }
    submitAssessment(password, answers, consentGiven) {
        return request("/assessments", {
            method: "POST",
            body: JSON.stringify({
                password,
                answers,
                consent_given: !!consentGiven,
            }),
        });
    },
 
    // POST /api/analyze -> stateless analysis (never saved)
    analyze(password, answers) {
        return request("/analyze", {
            method: "POST",
            body: JSON.stringify({ password, answers }),
        });
    },

    // POST /api/password-check -> password-only strength check
    passwordCheck(password) {
        return request("/password-check", {
            method: "POST",
            body: JSON.stringify({ password }),
        });
    },
 
    // GET /api/assessments -> { assessments: [...], count } (needs auth)
    getHistory() {
        return request("/assessments", { method: "GET" });
    },
 
    // GET /api/assessments/:id -> full stored detail (needs auth)
    getAssessment(id) {
        return request(`/assessments/${id}`, { method: "GET" });
    },
 
    // PATCH /api/recommendations/:id -> mark done/undone (needs auth)
    setRecommendationDone(id, completed) {
        return request(`/recommendations/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ completed: !!completed }),
        });
    },
 
    // auth
    getPublicConfig() {
        return request("/public-config", { method: "GET" });
    },
    googleLogin(credential) {
        return request("/google-login", {
            method: "POST",
            body: JSON.stringify({ credential }),
        });
    },
    register(fullName, email, password) {
        return request("/register", {
            method: "POST",
            body: JSON.stringify({ full_name: fullName, email, password }),
        });
    },
    login(email, password) {
        return request("/login", {
            method: "POST",
            body: JSON.stringify({ email, password }),
        });
    },
    logout() {
        return request("/logout", { method: "POST" });
    },
    me() {
        return request("/me", { method: "GET" });
    },
};