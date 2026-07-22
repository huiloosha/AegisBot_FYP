/* ============================================================
   AegisBot — login / register page
   Two forms in one page; toggles between them. On success stores
   the auth token (via api.saveToken) and redirects to dashboard.
   ============================================================ */

const loginCard    = document.getElementById("loginCard");
const registerCard = document.getElementById("registerCard");

/* ---- Toggle between the two forms ---- */
document.getElementById("toRegister").addEventListener("click", function (e) {
    e.preventDefault();
    loginCard.classList.add("auth__card--hidden");
    registerCard.classList.remove("auth__card--hidden");
});
document.getElementById("toLogin").addEventListener("click", function (e) {
    e.preventDefault();
    registerCard.classList.add("auth__card--hidden");
    loginCard.classList.remove("auth__card--hidden");
});

/* ---- Forgot password: not implemented in this prototype ---- */
document.getElementById("forgotLink").addEventListener("click", function (e) {
    e.preventDefault();
    const err = document.getElementById("loginError");
    err.textContent = "Password reset isn't available in this prototype yet.";
});

/* Note: we intentionally do NOT auto-redirect logged-in users away from this
   page. A stored token can be stale (e.g. the account was removed when the
   database was reset), which would bounce the user to the dashboard and then
   back here with a 401 — an inescapable loop. Letting the login page always
   open lets them simply log in again. */

/* ---- Login ---- */
const loginBtn = document.getElementById("loginBtn");
loginBtn.addEventListener("click", async function () {
    const email    = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;
    const err      = document.getElementById("loginError");
    err.textContent = "";

    if (!email || !password) {
        err.textContent = "Please enter your email and password.";
        return;
    }

    loginBtn.disabled = true;
    loginBtn.textContent = "Signing in…";
    try {
        const res = await api.login(email, password);
        api.saveToken(res.token);          // store token for future requests
        window.location.href = "dashboard.html";
    } catch (e) {
        err.textContent = e.message;       // e.g. "Invalid email or password."
        loginBtn.disabled = false;
        loginBtn.textContent = "Login";
    }
});

/* ---- Register ---- */
const registerBtn = document.getElementById("registerBtn");
registerBtn.addEventListener("click", async function () {
    const name     = document.getElementById("regName").value.trim();
    const email    = document.getElementById("regEmail").value.trim();
    const password = document.getElementById("regPassword").value;
    const confirm  = document.getElementById("regConfirm").value;
    const err      = document.getElementById("registerError");
    err.textContent = "";

    // client-side checks before hitting the server
    if (!name || !email || !password) {
        err.textContent = "Please fill in all fields.";
        return;
    }
    if (password.length < 8) {
        err.textContent = "Password must be at least 8 characters.";
        return;
    }
    if (password !== confirm) {
        err.textContent = "Passwords do not match.";
        return;
    }

    registerBtn.disabled = true;
    registerBtn.textContent = "Creating account…";
    try {
        const res = await api.register(name, email, password);
        api.saveToken(res.token);          // register also logs in (returns token)
        window.location.href = "dashboard.html";
    } catch (e) {
        err.textContent = e.message;       // e.g. "That email is already registered."
        registerBtn.disabled = false;
        registerBtn.textContent = "Register";
    }
});

/* ---- Enter key submits the visible form ---- */
document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    if (!loginCard.classList.contains("auth__card--hidden")) loginBtn.click();
    else registerBtn.click();
});

/* ---- Google Identity Services ---- */
async function handleGoogleCredential(response) {
    const loginError = document.getElementById("loginError");
    const registerError = document.getElementById("registerError");
    loginError.textContent = "";
    registerError.textContent = "";

    try {
        const res = await api.googleLogin(response.credential);
        api.saveToken(res.token);
        window.location.href = "dashboard.html";
    } catch (e) {
        const target = loginCard.classList.contains("auth__card--hidden")
            ? registerError
            : loginError;
        target.textContent = e.message;
    }
}

async function initGoogleSignIn() {
    try {
        const config = await api.getPublicConfig();
        if (!config.google_client_id) return;

        // GIS may finish loading after this script, so wait briefly for it.
        for (let i = 0; i < 50 && !window.google?.accounts?.id; i++) {
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        if (!window.google?.accounts?.id) return;

        google.accounts.id.initialize({
            client_id: config.google_client_id,
            callback: handleGoogleCredential,
        });

        ["googleLoginButton", "googleRegisterButton"].forEach(function (id) {
            const el = document.getElementById(id);
            if (el) {
                google.accounts.id.renderButton(el, {
                    theme: "outline",
                    size: "large",
                    width: 320,
                    text: "continue_with",
                    shape: "rectangular",
                });
            }
        });
    } catch (e) {
        console.error("Google Sign-In initialization failed:", e);
    }
}

initGoogleSignIn();