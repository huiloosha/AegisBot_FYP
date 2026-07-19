/* ============================================================
   AegisBot — recommendations page
   Reads the analysis result saved by the assessment page
   (sessionStorage) and renders the personalized security plan:
   Today's Priority, recommendation cards, a potential-improvement
   gauge, and good security habits.
   ============================================================ */

/* ---- GAUGE CONFIG (same palette as result page) ---- */
const GAUGE = {
    track: "#E5EAFC",
    thicknessRatio: 0.13,
    knob: true,
    knobRingWidth: 6,
    colours: {
        good:   "rgba(127, 228, 126, 1)",
        medium: "rgba(255, 235, 58, 1)",
        poor:   "rgba(255, 113, 139, 1)",
    },
    goodAt: 70,
    mediumAt: 40,
};

function scoreColour(score) {
    if (score >= GAUGE.goodAt)   return GAUGE.colours.good;
    if (score >= GAUGE.mediumAt) return GAUGE.colours.medium;
    return GAUGE.colours.poor;
}

/* Semicircular SVG gauge (same as result page). */
function gaugeSVG(pct, colour, size) {
    size = size || 220;
    pct = Math.max(0, Math.min(pct, 100));
    const stroke = size * GAUGE.thicknessRatio;
    const r  = (size - stroke) / 2;
    const cx = size / 2, cy = size / 2;
    const semi = Math.PI * r;
    const filled = (pct / 100) * semi;
    const height = size / 2 + stroke;
    const arc = `M ${stroke/2} ${cy} A ${r} ${r} 0 0 1 ${size - stroke/2} ${cy}`;
    const angle = Math.PI - (pct / 100) * Math.PI;
    const knobX = cx + r * Math.cos(angle);
    const knobY = cy - r * Math.sin(angle);
    const knob = GAUGE.knob ? `
        <circle cx="${knobX}" cy="${knobY}" r="${stroke*0.55}" fill="white"/>
        <circle cx="${knobX}" cy="${knobY}" r="${stroke*0.55 - GAUGE.knobRingWidth/2}"
                fill="none" stroke="${colour}" stroke-width="${GAUGE.knobRingWidth}"/>` : "";
    return `
    <svg width="${size}" height="${height}" viewBox="0 0 ${size} ${height}" style="overflow:visible">
        <path d="${arc}" fill="none" stroke="${GAUGE.track}" stroke-width="${stroke}" stroke-linecap="round"/>
        <path d="${arc}" fill="none" stroke="${colour}" stroke-width="${stroke}"
              stroke-linecap="round" stroke-dasharray="${filled} ${semi}"/>
        ${knob}
    </svg>`;
}

/* ---- Difficulty + impact helpers (derived from the recommendation) ---- */
// The backend gives priority (high/medium/low) and a numeric contribution.
// We turn those into the design's Impact stars and Difficulty label.
function impactStars(priority) {
    if (priority === "high")   return "★★★★★";
    if (priority === "medium") return "★★★☆☆";
    return "★★☆☆☆";
}
function difficultyLabel(code) {
    // Password fixes and MFA toggles are quick; behaviour change is harder.
    if (!code) return "Medium";
    if (code.startsWith("PW_") || code === "AUTH01" || code === "AUTH03") return "Easy";
    if (code.startsWith("SOC") || code.startsWith("PHISH")) return "Medium";
    return "Medium";
}
function priorityWord(priority) {
    return priority ? priority.charAt(0).toUpperCase() + priority.slice(1) : "Medium";
}

/* ---- Render the whole plan ---- */
function render(result) {
    const plan = result.recommendations_plan || {};
    const recos = plan.recommendations || [];

    // --- Today's Priority: the top recommendation ---
    if (recos.length > 0) {
        const top = recos[0];
        document.getElementById("priorityTitle").textContent = top.issue || top.action;
        // "Estimated impact" from its contribution to risk (rounded points).
        const impact = Math.round(top.contribution || 0);
        document.getElementById("priorityImpact").textContent =
            impact > 0 ? `Estimated impact: +${impact} cyber risk points` : "";
        document.getElementById("priorityTime").textContent =
            difficultyLabel(top.code) === "Easy" ? "Estimated time: ~2 minutes" : "Estimated time: a few minutes";
    } else {
        // No issues -> hide the priority block content
        document.getElementById("priorityTitle").textContent = "You're in great shape!";
        document.getElementById("priorityImpact").textContent =
            "No high-priority actions right now.";
        document.getElementById("priorityTime").textContent = "";
    }

    const cards = document.getElementById("cards");
cards.innerHTML = "";

if (recos.length === 0) {
    const p = document.createElement("p");
    p.className = "recs__empty";
    p.textContent =
        "No major issues were found in your assessment. Great work!";

    cards.appendChild(p);
} else {
    recos.forEach(function (r) {
        const card = document.createElement("div");
        card.className = "recs__card";

        card.innerHTML = `
            <div class="recs__card-inner">

                <!-- Front side -->
                <div class="recs__card-front">
                    <h3 class="recs__card-title">
                        ${r.issue || r.action}
                    </h3>

                    <p class="recs__card-desc">
                        ${r.action || ""}
                    </p>

                    <div class="recs__card-meta">
                        <div class="recs__card-row">
                            <span class="recs__card-key">
                                Priority
                            </span>

                            <span class="recs__card-badge recs__card-badge--${r.priority}">
                                ${priorityWord(r.priority)}
                            </span>
                        </div>

                        <div class="recs__card-row">
                            <span class="recs__card-key">
                                Impact
                            </span>

                            <span class="recs__card-stars">
                                ${impactStars(r.priority)}
                            </span>
                        </div>

                        <div class="recs__card-row">
                            <span class="recs__card-key">
                                Difficulty
                            </span>

                            <span class="recs__card-val">
                                ${difficultyLabel(r.code)}
                            </span>
                        </div>
                    </div>
                </div>

                <button
                    class="recs__card-why"
                    type="button"
                >
                    💡 Why?
                </button>

                <!-- Back side -->
                <div class="recs__card-back">
                    <p class="recs__card-evidence">
                        ${r.evidence || "No additional evidence available."}
                    </p>

                    <button
                        class="recs__card-why recs__card-why--back"
                        type="button"
                    >
                        Back
                    </button>
                </div>

            </div>
        `;

        const whyBtn = card.querySelector(".recs__card-why");
        const backBtn = card.querySelector(".recs__card-why--back");

        whyBtn.addEventListener("click", function () {
            card.classList.add("recs__card--flipped");
        });

        backBtn.addEventListener("click", function () {
            card.classList.remove("recs__card--flipped");
        });

        cards.appendChild(card);
    });
}

    // --- Potential improvement gauge ---
    // If the user fixes the issues, their safety would rise. We estimate the
    // improved safety as current safety + the total contribution of shown recos
    // (capped at 100). Current safety = avg(behaviour, password).
    const curSafety = Math.round(((result.behaviour_score ?? 0) + (result.password_score ?? 0)) / 2);
    const recoverable = recos.reduce(function (sum, r) { return sum + (r.contribution || 0); }, 0);
    const improved = Math.min(100, Math.round(curSafety + recoverable));
    const impColour = scoreColour(improved);
    const impWord = improved >= GAUGE.goodAt ? "LOW RISK"
                  : improved >= GAUGE.mediumAt ? "MEDIUM RISK" : "HIGH RISK";
    document.getElementById("improvementGauge").innerHTML =
        gaugeSVG(improved, impColour, 240) +
        `<div class="gauge__center">
            <div class="gauge__value-imp">${improved}%</div>
            <div class="gauge__label-imp">${impWord}</div>
         </div>`;

    // --- Good security habits (positives inferred from scores/features) ---
    const habits = document.getElementById("habitsList");
    habits.innerHTML = "";
    const pf = result.password_features || {};
    const positives = [];
    if ((result.password_score ?? 0) >= 70) positives.push("Strong password complexity");
    if (pf.has_symbol && pf.has_number && pf.has_uppercase) positives.push("Good character variety in passwords");
    if (!pf.common_pattern_detected) positives.push("No common password patterns detected");
    if ((result.behaviour_score ?? 0) >= 70) positives.push("Solid day-to-day security habits");
    if (positives.length === 0) positives.push("Completing this assessment is a great first step");
    positives.forEach(function (t) {
        const li = document.createElement("li");
        li.className = "recs__habits-item";
        li.textContent = t;
        habits.appendChild(li);
    });
}

/* ---- Entry point (same toggle pattern as result page) ---- */
(function () {
    const loading = document.getElementById("loading");
    const plan    = document.getElementById("plan");

    function showLoading(msg) {
        loading.classList.remove("loading--hide");
        loading.classList.remove("is-hidden");
        plan.classList.add("recs__plan--hidden");
        if (msg) {
            const t = loading.querySelector(".loading__text");
            if (t) t.textContent = msg;
        }
    }
    function showPlan() {
        loading.classList.add("loading--hide");
        loading.classList.add("is-hidden");
        plan.classList.remove("recs__plan--hidden");
    }

    const raw = sessionStorage.getItem("aegisbot_result");
    if (!raw) { showLoading(); return; }
    try {
        render(JSON.parse(raw));
        showPlan();
    } catch (err) {
        showLoading("Could not read your results. Please retake the assessment.");
    }
})();