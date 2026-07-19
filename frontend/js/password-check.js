/* ============================================================
   AegisBot — password check page
   Sends a password to /api/password-check and renders health
   gauge, breakdown, dictionary-word flag, and recommendations.
   ============================================================ */

/* ---- gauge (same style as other pages) ---- */
const GAUGE = {
    track: "#E5EAFC", thicknessRatio: 0.13, knob: true, knobRingWidth: 6,
    colours: { good: "rgba(127,228,126,1)", medium: "rgba(255,235,58,1)", poor: "rgba(255,113,139,1)" },
    goodAt: 70, mediumAt: 40,
};
function scoreColour(s) {
    if (s >= GAUGE.goodAt) return GAUGE.colours.good;
    if (s >= GAUGE.mediumAt) return GAUGE.colours.medium;
    return GAUGE.colours.poor;
}
function gaugeSVG(pct, colour, size) {
    size = size || 200; pct = Math.max(0, Math.min(pct, 100));
    const stroke = size * GAUGE.thicknessRatio, r = (size - stroke) / 2;
    const cx = size / 2, cy = size / 2, semi = Math.PI * r, filled = (pct / 100) * semi;
    const height = size / 2 + stroke;
    const arc = `M ${stroke/2} ${cy} A ${r} ${r} 0 0 1 ${size - stroke/2} ${cy}`;
    const angle = Math.PI - (pct / 100) * Math.PI;
    const kx = cx + r * Math.cos(angle), ky = cy - r * Math.sin(angle);
    const knob = GAUGE.knob ? `
        <circle cx="${kx}" cy="${ky}" r="${stroke*0.55}" fill="white"/>
        <circle cx="${kx}" cy="${ky}" r="${stroke*0.55 - GAUGE.knobRingWidth/2}"
                fill="none" stroke="${colour}" stroke-width="${GAUGE.knobRingWidth}"/>` : "";
    return `<svg width="${size}" height="${height}" viewBox="0 0 ${size} ${height}" style="overflow:visible">
        <path d="${arc}" fill="none" stroke="${GAUGE.track}" stroke-width="${stroke}" stroke-linecap="round"/>
        <path d="${arc}" fill="none" stroke="${colour}" stroke-width="${stroke}"
              stroke-linecap="round" stroke-dasharray="${filled} ${semi}"/>${knob}</svg>`;
}
function scoreWord(s) {
    if (s >= 85) return "Excellent";
    if (s >= 70) return "Strong Enough";
    if (s >= 50) return "Fair";
    if (s >= 30) return "Weak";
    return "Very Weak";
}

const el = {
    input:   document.getElementById("pwInput"),
    btn:     document.getElementById("analyzeBtn"),
    error:   document.getElementById("pwError"),
    results: document.getElementById("results"),
};

function render(data) {
    const f = data.password_features;
    const score = Math.round(data.password_score);

    // Health gauge
    document.getElementById("healthGauge").innerHTML =
        gaugeSVG(score, scoreColour(score), 190) +
        `<div class="gauge__center"><div class="gauge__value-pwdch">${score}%</div></div>`;
    document.getElementById("healthWord").textContent = scoreWord(score);

    // Length bar (map length to a 0-100 feel: 16+ = full)
    const lengthPct = Math.min(100, Math.round((f.password_length / 16) * 100));
    document.getElementById("lengthBar").style.width = lengthPct + "%";
    document.getElementById("lengthNote").textContent =
        f.password_length >= 12 ? "✓ Excellent"
        : f.password_length >= 8 ? "Acceptable, longer is better"
        : "✗ Too short";

    // Character variety
    const classes = [
        { key: "has_uppercase", label: "Uppercase" },
        { key: "has_lowercase", label: "Lowercase" },
        { key: "has_number",    label: "Numbers" },
        { key: "has_symbol",    label: "Symbols" },
    ];
    const present = classes.filter(c => f[c.key]).length;
    document.getElementById("varietyBar").style.width = (present / 4 * 100) + "%";
    const vl = document.getElementById("varietyList");
    vl.innerHTML = "";
    classes.forEach(c => {
        const li = document.createElement("li");
        li.className = "pwc__variety-item" + (f[c.key] ? " pwc__variety-item--yes" : "");
        li.textContent = (f[c.key] ? "✓ " : "✗ ") + c.label;
        vl.appendChild(li);
    });

    // Dictionary words
    const dictIcon = document.getElementById("dictIcon");
    const dictNote = document.getElementById("dictNote");
    if (f.common_pattern_detected) {
        dictIcon.innerHTML = '<img src="images/dangerous.svg" alt="Warning" class="pwc__dict-img">';
        dictIcon.className = "pwc__dict-icon pwc__dict-icon--warn";
        dictNote.textContent = "Common word detected";
    } else {
        dictIcon.innerHTML = '<img src="images/safe.svg" alt="Warning" class="pwc__dict-img">';
        dictIcon.className = "pwc__dict-icon pwc__dict-icon--ok";
        dictNote.textContent = "No common words detected";
    }

    // Recommendations
    const recs = [];
    if (f.password_length < 12) recs.push("Use at least 12 characters — length is the biggest factor in strength.");
    if (present < 4) recs.push("Mix upper- and lower-case letters, numbers, and symbols.");
    if (f.common_pattern_detected) recs.push("Avoid predictable words, names, or common sequences.");
    if (f.repeated_characters) recs.push("Avoid repeated character runs (e.g. 'aaa', '111').");
    if (recs.length === 0) recs.push("Great password! Keep using unique passwords for each account.");
    const ul = document.getElementById("pwRecs");
    ul.innerHTML = "";
    recs.forEach(t => { const li = document.createElement("li"); li.className = "pwc__recs-item"; li.textContent = t; ul.appendChild(li); });

    el.results.classList.remove("is-hidden");
}

async function analyze() {
    const pw = el.input.value;
    el.error.textContent = "";
    if (!pw) { el.error.textContent = "Please enter a password to analyse."; return; }

    el.btn.disabled = true;
    el.btn.textContent = "Analysing…";
    try {
        const data = await api.passwordCheck(pw);
        render(data);
    } catch (e) {
        el.error.textContent = e.message;
    } finally {
        el.btn.disabled = false;
        el.btn.textContent = "Start Analysis";
    }
}

el.btn.addEventListener("click", analyze);
el.input.addEventListener("keydown", e => { if (e.key === "Enter") analyze(); });