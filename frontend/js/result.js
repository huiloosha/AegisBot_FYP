/* ============================================================
   AegisBot — result page
   Reads the analysis result saved by the assessment page (in
   sessionStorage) and renders the risk report.
   ============================================================ */

/* ---- GAUGE STYLE CONFIG ----
   All the visual "knobs" for the gauges live here, so you can restyle
   without touching the drawing code below. Colours are from the Figma design. */
const GAUGE = {
    track: "#E5EAFC",          // colour of the empty part of the arc
    thicknessRatio: 0.13,      // arc thickness as a fraction of size (0.13 ≈ Figma)
    knob: true,                // show the round knob at the end of the fill
    knobRingWidth: 6,          // white knob's coloured ring thickness

    // Threshold palette (used by BOTH sub-gauges and the main gauge).
    // A score/percentage is "good" when high, so:
    colours: {
        good:   "rgba(127, 228, 126, 1)",   // green   (high score = safe)
        medium: "rgba(255, 235, 58, 1)",    // yellow  (middle)
        poor:   "rgba(255, 113, 139, 1)",   // pink/red(low score = risky)
    },
    // score cut-offs for the colour bands
    goodAt:   70,   // >= 70 -> green
    mediumAt: 40,   // >= 40 -> yellow, else pink
};

/* Pick a fill colour from a 0-100 SAFETY score (higher = safer). */
function scoreColour(score) {
    if (score >= GAUGE.goodAt)   return GAUGE.colours.good;
    if (score >= GAUGE.mediumAt) return GAUGE.colours.medium;
    return GAUGE.colours.poor;
}

/* Main gauge colour by risk CLASS (Low good, High poor). */
function riskColour(riskClass) {
    if (riskClass === "Low")      return GAUGE.colours.good;
    if (riskClass === "Moderate") return GAUGE.colours.medium;
    return GAUGE.colours.poor;   // High
}

/* ---- Build a semicircular SVG gauge ----
   pct    : 0-100, how much of the arc to fill.
   colour : the fill colour (already chosen by scoreColour / riskColour).
   size   : overall width in px.
   Returns an SVG string: a grey track arc + a coloured fill arc + a knob. */
function gaugeSVG(pct, colour, size, svgHeight) {
    size = size || 220;
    svgHeight = svgHeight || (size / 2 + size * GAUGE.thicknessRatio);
    pct = Math.max(0, Math.min(pct, 100));

    const stroke = size * GAUGE.thicknessRatio;   // arc thickness
    const r  = (size - stroke) / 2;               // radius (fits inside width)
    const cx = size / 2;
    const cy = size / 2;                            // baseline (bottom of semicircle)
    const semi   = Math.PI * r;                     // length of a half circle
    const filled = (pct / 100) * semi;              // length to colour in
    const height = svgHeight;               // just the top half + padding

    // The arc path: from left, over the top, to the right.
    const arc = `M ${stroke/2} ${cy} A ${r} ${r} 0 0 1 ${size - stroke/2} ${cy}`;

    // Knob position = end of the filled arc (angle goes 180°→0° as pct 0→100).
    const angle = Math.PI - (pct / 100) * Math.PI;
    const knobX = cx + r * Math.cos(angle);
    const knobY = cy - r * Math.sin(angle);

    const knob = GAUGE.knob ? `
        <circle cx="${knobX}" cy="${knobY}" r="${stroke*0.55}"
                fill="white"/>
        <circle cx="${knobX}" cy="${knobY}" r="${stroke*0.55 - GAUGE.knobRingWidth/2}"
                fill="none" stroke="${colour}" stroke-width="${GAUGE.knobRingWidth}"/>
    ` : "";

    return `
    <svg width="${size}" height="${height}" viewBox="0 0 ${size} ${height}"
         style="overflow:visible">
        <path
            d="${arc}"
            fill="none"
            stroke="${GAUGE.track}"
            stroke-width="${stroke}"
            stroke-linecap="round"
        />

        <path
            d="${arc}"
            fill="none"
            stroke="${colour}"
            stroke-width="${stroke}"
            stroke-linecap="round"
            stroke-dasharray="${filled} ${semi}"
            stroke-dashoffset="0"
        />
        ${knob}
    </svg>`;
}

/* Small word for a password/behaviour score. */
function scoreWord(score) {
    if (score >= 85) return "Excellent";
    if (score >= 70) return "Strong";
    if (score >= 50) return "Fair";
    if (score >= 30) return "Weak";
    return "Poor";
}

function render(result) {
    // ---- Big overall gauge ----
    // We show the probability of the PREDICTED class as the headline number,
    // and the class word (LOW/MEDIUM/HIGH) under it.
    const bScore = Math.round(Number(result.behaviour_score) || 0);
    const pScore = Math.round(Number(result.password_score) || 0);
    const overallScore = Math.round((bScore + pScore) / 2);

    function riskModifier(riskClass) {
        switch (riskClass) {
            case "Low":
                return "gauge__label";

            case "Moderate":
                return "gauge__label--medium";

            case "High":
                return "gauge__label--high";

            default:
                return "";
        }
    }

    let riskClass;

    if (overallScore >= 70) {
        riskClass = "Low";
    } else if (overallScore >= 40) {
        riskClass = "Moderate";
    } else {
        riskClass = "High";
    }

    const classWord =
        riskClass === "Moderate"
            ? "MEDIUM"
            : riskClass.toUpperCase();

    const overallColour = scoreColour(overallScore);

    function valueModifier(value) {
        if (value < 10) {
            return "gauge__value--short";
        }

        if (value < 100) {
            return "gauge__value";
        }

        return "gauge__value--long";
    }

    document.getElementById("mainGauge").innerHTML =
        gaugeSVG(overallScore, overallColour, 416, 215) +
        `<div class="gauge__center">
            <div class="gauge__value ${valueModifier(overallScore)}">${overallScore}%</div>
            <div class="gauge__label ${riskModifier(riskClass)}">${classWord}</div>
         </div>`;

    // summary line
    const summaries = {
        Low: "Your cybersecurity practices are strong. Keep it up!",
        Moderate: "Your cybersecurity practices are generally good, but several improvements are recommended.",
        High: "Your cybersecurity practices need attention. Follow the recommendations to reduce your risk.",
    };
    document.getElementById("summaryText").textContent =
        summaries[riskClass] || "";

    // ---- Behaviour sub-gauge ----
    document.getElementById("behaviourGauge").innerHTML =
        gaugeSVG(bScore, scoreColour(bScore), 262, 140) +
        `<div class="subgauge__value">${bScore}</div>`;
    document.getElementById("behaviourNote").textContent = scoreWord(bScore);

    // ---- Password sub-gauge ----
    document.getElementById("passwordGauge").innerHTML =
        gaugeSVG(pScore, scoreColour(pScore), 262, 140) +
        `<div class="subgauge__value subgauge__value--pwd">${pScore}%</div>`;
    document.getElementById("passwordNote").textContent = scoreWord(pScore);

    // ---- Strengths / improvements from the recommendations plan ----
    // Improvements = the top recommendations (issues found).
    // Strengths = a few positive notes derived from good scores.
    const plan = result.recommendations_plan || {};
    const recos = plan.recommendations || [];

    const improvements = document.getElementById("improvementsList");
    improvements.innerHTML = "";
    if (recos.length === 0) {
        const li = document.createElement("li");
        li.textContent = "No major issues found — great work!";
        improvements.appendChild(li);
    } else {
        recos.slice(0, 4).forEach(function (r) {
            const li = document.createElement("li");
            li.textContent = r.issue || r.action || r.code;
            improvements.appendChild(li);
        });
    }

    // Strengths: infer from scores (simple, honest positives).
    const strengths = document.getElementById("strengthsList");
    strengths.innerHTML = "";
    const positives = [];
    if (pScore >= 70) positives.push("Strong password strength.");
    if (bScore >= 70) positives.push("Good day-to-day security habits.");
    const pf = result.password_features || {};
    if (pf.has_symbol && pf.has_number) positives.push("Password uses a good character mix.");
    if (!pf.common_pattern_detected) positives.push("No common password patterns detected.");
    if (positives.length === 0) positives.push("Completing this assessment is a great first step.");
    positives.forEach(function (t) {
        const li = document.createElement("li");
        li.textContent = t;
        strengths.appendChild(li);
    });

    // ---- Insights (plain-language paragraph) ----
    const lines = [];
    if (pScore >= 85) lines.push("Your password security is excellent.");
    else if (pScore < 50) lines.push("Your password could be significantly stronger.");
    if (bScore < 70) {
        lines.push("Most of your cyber risk is associated with daily online behaviour rather than password strength.");
        lines.push("Improving your everyday habits could significantly reduce your overall risk.");
    }
    lines.push("");
    lines.push(`Overall, your current cyber hygiene level is ${classWord.toLowerCase()}.`);
    lines.push("Based on your responses, the system identified areas that may increase your cybersecurity risk. Improving these may reduce your future exposure to cyber threats.");
    document.getElementById("insightsText").textContent = lines.join("\n");
}

// ---- Entry point ----
// Toggles between the "loading / no results" message and the report,
// using the exact class names defined in the CSS:
//   loading            -> visible; loading--hide -> faded out
//   result__report--hidden -> hidden; result__report--show -> shown (animated)
(function () {
    const loading = document.getElementById("loading");
    const report  = document.getElementById("report");

    function showLoading(message) {
        // show the loading block, hide the report
        loading.classList.remove("loading--hide");
        report.classList.remove("result__report--show");
        report.classList.add("result__report--hidden");
        if (message) {
            const t = loading.querySelector(".loading__text");
            if (t) t.textContent = message;
        }
    }

    function showReport() {
        // hide loading (also remove it from layout so it leaves no empty space),
        // then reveal the report with the CSS appear-animation.
        loading.classList.add("loading--hide");
        loading.classList.add("is-hidden");            // display:none -> no leftover gap
        report.classList.remove("result__report--hidden");
        report.classList.add("result__report--show");
    }

    async function loadResult() {
        const raw = sessionStorage.getItem("aegisbot_result");
        if (raw) {
            try {
                render(JSON.parse(raw));
                showReport();
                return;
            } catch (_) {
                sessionStorage.removeItem("aegisbot_result");
            }
        }

        // "Last Results" must also work after refresh/new browser tab. For a
        // logged-in user, load their newest persisted assessment from the API.
        if (api.isLoggedIn()) {
            try {
                const history = await api.getHistory();
                const latest = history.assessments && history.assessments[0];
                if (latest) {
                    const result = await api.getAssessment(latest.assessment_id);
                    sessionStorage.setItem("aegisbot_result", JSON.stringify(result));
                    render(result);
                    showReport();
                    return;
                }
            } catch (err) {
                console.error("Could not load last result:", err);
            }
        }

        showLoading("No saved results yet. Complete an assessment first.");
    }

    loadResult();
})();