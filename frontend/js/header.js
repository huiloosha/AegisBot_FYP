/* ============================================================
   AegisBot — smart header
   On every page that includes this script, the nav "Log In" button
   becomes "Logout" when the user is logged in. Clicking Logout calls
   the backend, clears the token, and returns to the landing page.
   Attach by class (.nav__login) so no per-page id is needed.
   ============================================================ */
(function () {
    const loginBtn = document.querySelector(".nav__login");
    if (!loginBtn) return;   // page has no nav login button
 
    if (api.isLoggedIn()) {
        // Logged in -> turn the button into a Logout action.
        loginBtn.textContent = "Logout";
        loginBtn.setAttribute("href", "#");
        loginBtn.addEventListener("click", async function (e) {
            e.preventDefault();
            try {
                await api.logout();      // revoke the token on the server
            } catch (_) {
                // even if the server call fails, we still log out locally
            }
            api.clearToken();            // remove the local token
            window.location.href = "landing.html";
        });
    }
    // Not logged in -> leave it as the default "Log In" link to login.html.
})();
