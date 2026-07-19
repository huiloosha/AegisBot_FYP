// Answer options per response_type. The user sees a LABEL; the model
// stores a VALUE 0-4. Direction (direct/reverse) is handled server-side,
// so 0..4 always follows the label order below.
const OPTION_SETS = {
    frequency: [
        { label: "Never",     value: 0 },
        { label: "Rarely",    value: 1 },
        { label: "Sometimes", value: 2 },
        { label: "Often",     value: 3 },
        { label: "Always",    value: 4 },
    ],
    scale: [
        { label: "Very low",  value: 0 },
        { label: "Low",       value: 1 },
        { label: "Moderate",  value: 2 },
        { label: "High",      value: 3 },
        { label: "Very high", value: 4 },
    ],
    yes_no: [
        { label: "No",  value: 0 },
        { label: "Yes", value: 4 },
    ],
};

const CATEGORY_LABELS = {
    PM: "Password Security",
    AUTH: "Authentication / MFA",
    PHISH: "Phishing & Awareness",
    SOC: "Social Media Exposure",
};

// ---- State ----
let questions = [];
let current = 0;
let answers = {};
let onPasswordStep = false;

// ---- Element references ----
const el = {
    loading:       document.getElementById("loading"),
    assess:        document.getElementById("assess"),
    sidebar:            document.getElementById("assessmentSidebar"),
    assessmentProgress: document.getElementById("assessmentProgress"),
    progressBar:   document.getElementById("progressBar"),
    progressLabel: document.getElementById("progressLabel"),
    questionView:  document.getElementById("questionView"),
    passwordView:  document.getElementById("passwordView"),
    qCategory:     document.getElementById("qCategory"),
    qText:         document.getElementById("qText"),
    qWhy:          document.getElementById("qWhy"),
    options:       document.getElementById("options"),
    pwInput:       document.getElementById("pwInput"),
    backBtn:       document.getElementById("backBtn"),
    nextBtn:       document.getElementById("nextBtn"),
    errorMsg:      document.getElementById("errorMsg"),
};

function wait(ms) {
    return new Promise(function (resolve) {
        setTimeout(resolve, ms);
    });
}

// ---- Load questions on page open ----
async function init() {
    // Hide the assessment grid until questions arrive; show loading.
    el.loading.classList.remove("loading--hide");

    el.assess.classList.add("assessment-grid--hidden");
    el.assess.classList.remove("assessment-grid--show");
    try {
        const [data] = await Promise.all([
            api.getQuestions(),
            wait(3000),
        ]);
        questions = data.questions;
        el.loading.classList.add("loading--hide");
        await wait(500);
        el.loading.style.display = "none";
        el.assess.classList.remove("assessment-grid--hidden");
        el.assess.classList.add("assessment-grid--show");     // reveal (uses the CSS default: grid)
        render();
    } catch (err) {
        const loadingText = el.loading.querySelector(".loading__text");

        loadingText.style.animation = "none";
        loadingText.style.width = "auto";
        loadingText.style.overflow = "visible";
        loadingText.style.borderRight = "none";
        loadingText.style.whiteSpace = "normal";
        loadingText.style.textAlign = "center";

        loadingText.textContent =
            "Could not load questions. Is the backend running? (" +
            err.message +
            ")";
    }
}

// ---- Render current step ----
function render() {
    el.errorMsg.textContent = "";

    if (onPasswordStep) {
        el.questionView.classList.add("panel__question--hidden");
        el.passwordView.classList.remove("panel__question--hidden");
        el.sidebar.classList.add("is-hidden");
        el.assessmentProgress.classList.add("is-hidden");
        el.assess.classList.add("assessment-grid--password");
        el.nextBtn.textContent = "Get My Results";
        setProgress(100);
        updateSidebar(null);
        el.backBtn.disabled = false;
        return;
    }

    el.sidebar.classList.remove("is-hidden");
    el.assessmentProgress.classList.remove("is-hidden");
    el.assess.classList.remove("assessment-grid--password");
    el.questionView.classList.remove("panel__question--hidden");
    el.passwordView.classList.add("panel__question--hidden");
    el.nextBtn.textContent = "Next";

    const q = questions[current];
    el.qCategory.textContent = CATEGORY_LABELS[q.category] || q.category;
    el.qText.textContent = q.question_text;
    el.qWhy.textContent = q.explanation ? "Why this matters: " + q.explanation : "";

    // Build answer options for this question's response_type
    const set = OPTION_SETS[q.response_type] || OPTION_SETS.frequency;
    el.options.innerHTML = "";
    set.forEach(function (opt) {
        const div = document.createElement("div");
        div.className = "option";
        if (answers[q.question_code] === opt.value) div.classList.add("option--selected");
        div.innerHTML =
            '<span class="option__radio"></span><span class="option__label">' +
            opt.label + "</span>";
        div.addEventListener("click", function () {
            answers[q.question_code] = opt.value;
            render();
        });
        el.options.appendChild(div);
    });

    setProgress(Math.round((current / questions.length) * 100));
    updateSidebar(q.category);
    el.backBtn.disabled = (current === 0);
}

function setProgress(pct) {
    el.progressBar.style.width = pct + "%";
    const count = el.progressLabel.querySelector(".panel__progress-count");
    if (count) count.textContent = pct + "%";
    else el.progressLabel.textContent = pct + "%";
}

// Highlight active category, mark earlier ones done
function updateSidebar(activeCat) {
    const order = ["PM", "AUTH", "PHISH", "SOC"];
    const activeIdx = order.indexOf(activeCat);
    document.querySelectorAll(".assessment-grid__cat").forEach(function (node) {
        const cat = node.dataset.cat;
        node.classList.remove("assessment-grid__cat--active", "assessment-grid__cat--done");
        if (activeCat === null) {
            node.classList.add("assessment-grid__cat--done");
            return;
        }
        const idx = order.indexOf(cat);
        if (idx === activeIdx) node.classList.add("assessment-grid__cat--active");
        else if (idx < activeIdx) node.classList.add("assessment-grid__cat--done");
    });
}

// ---- Next ----
el.nextBtn.addEventListener("click", function () {
    if (onPasswordStep) { return submit(); }

    const q = questions[current];
    if (answers[q.question_code] === undefined) {
        el.errorMsg.textContent = "Please select an answer to continue.";
        return;
    }
    if (current < questions.length - 1) {
        current++;
        render();
    } else {
        onPasswordStep = true;
        render();
    }
});

// ---- Back ----
el.backBtn.addEventListener("click", function () {
    if (onPasswordStep) { onPasswordStep = false; render(); return; }
    if (current > 0) { current--; render(); }
});

// ---- Submit ----
async function submit() {
    const password = el.pwInput.value;
    if (!password) {
        el.errorMsg.textContent = "Please enter a password to analyse.";
        return;
    }
    el.nextBtn.disabled = true;
    el.nextBtn.textContent = "Analysing…";
    try {
        const consent = api.isLoggedIn();  // logged-in -> saved; guest -> not saved
        const result = await api.submitAssessment(password, answers, consent);
        sessionStorage.setItem("aegisbot_result", JSON.stringify(result));
        window.location.href = "result.html";
    } catch (err) {
        el.errorMsg.textContent = err.message;
        el.nextBtn.disabled = false;
        el.nextBtn.textContent = "Get My Results";
    }
}

init();