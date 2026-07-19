/* ============================================================
   AegisBot — dashboard page
   Requires login. Fetches the user's assessment history from the
   backend and renders: 4 stat gauges, a cyber-risk trend line
   chart (hand-drawn SVG), and a security checklist.
   ============================================================ */

/* ---- GAUGE CONFIG (same palette as result/recommendations) ---- */
const GAUGE = {
    track: "#E5EAFC",
    thicknessRatio: 0.14,
    knob: true,
    knobRingWidth: 5,
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
function gaugeSVG(pct, colour, size) {
    size = size || 160;
    pct = Math.max(0, Math.min(pct, 100));
    const stroke = size * GAUGE.thicknessRatio;
    const r = (size - stroke) / 2;
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

/* ---- Hand-drawn SVG line chart for the risk trend ----
   Styled to match the project's Graph.svg design:
   single #0075FF line, gradient fill beneath, dashed #56577A grid,
   #CBD5E0 axis labels.
   points: array of numbers (0-100), oldest first. */
function trendChartSVG(points) {
    const w = 882, h = 297;
    const padL = 41, padR = 2, padT = 7, padB = 40;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    if (points.length === 0) {
        return `<p style="color:rgba(255,255,255,0.5)">No trend data yet.</p>`;
    }
    // one point -> duplicate so a flat line is drawable
    const data = points.length === 1 ? [points[0], points[0]] : points;
    const n = data.length;

    const xAt = i => padL + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    const yAt = v => padT + (1 - v / 100) * plotH;

    // dashed horizontal gridlines + Y labels (0,20,40,60,80,100)
    let grid = "";
    for (let g = 0; g <= 100; g += 20) {
        const y = yAt(g);
        grid += `<line x1="${padL}" y1="${y}" x2="${w - padR}" y2="${y}"
                    stroke="#56577A" stroke-linecap="round"
                    stroke-dasharray="3.5 3.5"/>
                 <text x="${padL - 12}" y="${y + 4}" text-anchor="end"
                    fill="#CBD5E0" font-size="12">${g}</text>`;
    }

    // smooth-ish line via straight segments (data-driven)
    let line = "";
    data.forEach((v, i) => { line += (i === 0 ? "M" : "L") + xAt(i) + " " + yAt(v) + " "; });
    // area = line down to baseline and back
    const baseY = padT + plotH;
    const area = line + `L ${xAt(n - 1)} ${baseY} L ${xAt(0)} ${baseY} Z`;

    // dots on each data point
    let dots = "";
    data.forEach((v, i) => {
        dots += `<circle cx="${xAt(i)}" cy="${yAt(v)}" r="4" fill="#0075FF"/>`;
    });

    return `
    <svg width="100%" viewBox="0 0 ${w} ${h}">
        <defs>
            <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stop-color="#0075FF" stop-opacity="0.55"/>
                <stop offset="100%" stop-color="#0075FF" stop-opacity="0"/>
            </linearGradient>
        </defs>
        ${grid}
        <path d="${area}" fill="url(#trendFill)"/>
        <path d="${line}" fill="none" stroke="#0075FF" stroke-width="3"
              stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}
    </svg>`;
}

/* ---- Render dashboard from history + latest detail ---- */
function renderDashboard(history, userName) {
    document.getElementById("userName").textContent = userName || "there";

    // history comes newest-first; reverse for chronological trend
    const chrono = history.slice().reverse();
    const latest = history[0];   // newest

    // --- Stat gauges (from the latest assessment) ---
    // risk_score is probability of predicted class (0-1). We show SAFETY as
    // avg(behaviour, password), same as the result page's main gauge.
    const bScore = Math.round(latest.behaviour_score ?? 0);
    const pScore = Math.round(latest.password_score ?? 0);
    const safety = Math.round((bScore + pScore) / 2);

    document.getElementById("riskGauge").innerHTML =
        gaugeSVG(safety, scoreColour(safety), 150) +
        `<div class="gauge__center"><div class="gauge__value-dash">${safety}</div>
         <div class="gauge__label-dash">/100</div></div>`;
    document.getElementById("behaviourGauge").innerHTML =
        gaugeSVG(bScore, scoreColour(bScore), 150) +
        `<div class="gauge__center"><div class="gauge__value-dash">${bScore}</div>
         <div class="gauge__label-dash">/100</div></div>`;
    document.getElementById("passwordGauge").innerHTML =
        gaugeSVG(pScore, scoreColour(pScore), 150) +
        `<div class="gauge__center"><div class="gauge__value-dash">${pScore}</div>
         <div class="gauge__label-dash">/100</div></div>`;

    document.getElementById("completedCount").textContent = history.length;

    // --- Trend chart: safety over time (avg of behaviour+password per assessment) ---
    const trendPoints = chrono.map(a =>
        Math.round(((a.behaviour_score ?? 0) + (a.password_score ?? 0)) / 2));
    document.getElementById("trendChart").innerHTML = trendChartSVG(trendPoints);

    // delta since first assessment
    if (trendPoints.length >= 2) {
        const delta = trendPoints[trendPoints.length - 1] - trendPoints[0];
        const sign = delta >= 0 ? "+" : "";
        const el = document.getElementById("trendDelta");
        el.textContent = `${sign}${delta} points since your first assessment`;
        el.style.color = delta >= 0 ? "#7fe47e" : "#ff718b";
    } else {
        document.getElementById("trendDelta").textContent =
            "Complete more assessments to see your trend.";
    }

    // --- Security checklist (simple, from latest scores) ---
    // Marks items done based on the latest assessment's scores.
    const checklist = [
        { label: "Strong Password", done: pScore >= 70 },
        { label: "Good Behaviour Score", done: bScore >= 70 },
        { label: "Low Overall Risk", done: latest.risk_level === "Low" },
        { label: "Assessment Completed", done: true },
        { label: "Regular Re-assessment", done: history.length >= 2 },
    ];
    const ul = document.getElementById("checklist");
    ul.innerHTML = "";
    checklist.forEach(item => {
        const li = document.createElement("li");
        li.className = "dash__checklist-item" + (item.done ? " dash__checklist-item--done" : "");
        li.textContent = item.label;
        ul.appendChild(li);
    });
}

/* ---- Entry point: auth guard + fetch ---- */
(function () {
    const loading = document.getElementById("loading");
    const guest   = document.getElementById("guest");
    const empty   = document.getElementById("empty");
    const board   = document.getElementById("board");

    function show(activeElement) {
        const sections = [loading, guest, empty, board];

        sections.forEach(function (section) {
            section.classList.add("is-hidden");
        });

        activeElement.classList.remove("is-hidden");
    }

    show(loading);  

    // Not logged in -> show guest prompt (design requires login).
    if (!api.isLoggedIn()) {
        show(guest);
        return;
    }

    // Logged in -> fetch name + history.
    Promise.all([
        api.me(),
        api.getHistory()
    ])
        .then(function ([me, hist]) {
            const history = hist.assessments || [];

            if (history.length === 0) {
                show(empty);
                return;
            }

            renderDashboard(history, me.full_name);
            show(board);
        })
        .catch(function (err) {
            console.error("Dashboard loading error:", err);

            show(guest);
        });
})();