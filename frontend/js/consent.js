/* ============================================================
   AegisBot — consent modal
   Shows a research-consent overlay every time the user opens a page
   that includes it (assessment / password check). The page content
   stays blocked until the user ticks "I agree" and clicks Continue.
   No consent is remembered — it is asked on every visit, which is the
   more privacy-respecting choice for a research tool.
   ============================================================ */
(function () {
    const overlay  = document.getElementById("consentOverlay");
    const agreeBox  = document.getElementById("consentAgreeBox");
    const continueBtn = document.getElementById("consentContinue");

    if (!overlay || !agreeBox || !continueBtn) return;   // no modal on this page

    let agreed = false;   // tracks whether the custom checkbox is ticked

    // Continue is disabled until the box is ticked.
    continueBtn.disabled = true;

    // Clicking the custom radio toggles the agreement state + visual selection.
    agreeBox.addEventListener("click", function () {
        agreed = !agreed;
        agreeBox.classList.toggle("option--selected", agreed);
        continueBtn.disabled = !agreed;
    });

    // Agreeing hides the overlay and lets the user interact with the page.
    continueBtn.addEventListener("click", function () {
        if (!agreed) return;
        overlay.classList.add("consent--hidden");
    });
 
    // If the user declines (closes), send them back to the landing page —
    // they can't use the assessment/password tools without consenting.
    const declineBtn = document.getElementById("consentDecline");
    if (declineBtn) {
        declineBtn.addEventListener("click", function (e) {
            e.preventDefault();
            window.location.href = "landing.html";
        });
    }
})();