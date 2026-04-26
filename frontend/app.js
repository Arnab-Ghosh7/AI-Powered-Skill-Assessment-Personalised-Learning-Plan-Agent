const API_BASE_URL = "https://ai-powered-skill-assessment-personalised-4dl3.onrender.com";

/* ── State ── */
const state = {
  sessionId: null,
  totalSkills: 0,
  currentSkillIndex: 0,
  jdSkills: [],
  phase: "upload",
};

/* ── Helpers ── */
const $ = (id) => document.getElementById(id);
const show = (id) => $(id).classList.remove("hidden");
const hide = (id) => $(id).classList.add("hidden");

function showSpinner(text = "Thinking...") {
  $("spinner-text").textContent = text;
  show("spinner");
}
function hideSpinner() {
  hide("spinner");
}

function showError(id, msg) {
  const el = $(id);
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 5000);
}

/* ── File upload previews ── */
document.getElementById("jd-file").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (f) $("jd-file-name").textContent = f.name;
});
document.getElementById("resume-file").addEventListener("change", (e) => {
  const f = e.target.files[0];
  if (f) $("resume-file-name").textContent = f.name;
});

/* ── Enter to send ── */
document.getElementById("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

/* ── Step 1: Start assessment ── */
async function startAssessment() {
  const jdText = $("jd-textarea").value.trim();
  const resumeText = $("resume-textarea").value.trim();
  const jdFile = $("jd-file").files[0];
  const resumeFile = $("resume-file").files[0];

  if (!jdText && !jdFile) {
    showError("upload-error", "Please provide a job description — paste text or upload a file.");
    return;
  }
  if (!resumeText && !resumeFile) {
    showError("upload-error", "Please provide your resume — paste text or upload a file.");
    return;
  }

  showSpinner("Parsing your documents...");

  try {
    let finalJd = jdText;
    let finalResume = resumeText;

    // If files provided, upload them for parsing
    if (jdFile || resumeFile) {
      const form = new FormData();
      if (jdFile) form.append("jd_file", jdFile);
      else form.append("jd_text", jdText);
      if (resumeFile) form.append("resume_file", resumeFile);
      else form.append("resume_text", resumeText);
      const parseRes = await fetch(`${API_BASE_URL}/api/upload-text`, { method: "POST", body: form });
      if (!parseRes.ok) {
        const textToParse = await parseRes.text();
        try { throw new Error(JSON.parse(textToParse).detail); }
        catch (e) { throw new Error(e.message === "Unexpected token" ? textToParse : (JSON.parse(textToParse).detail || textToParse)); }
      }
      const parsed = await parseRes.json();
      finalJd = parsed.jd_text;
      finalResume = parsed.resume_text;
    }

    // Start session
    state.sessionId = crypto.randomUUID();
    showSpinner("Extracting skills from JD...");

    const startRes = await fetch(`${API_BASE_URL}/api/start-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        jd_text: finalJd,
        resume_text: finalResume,
      }),
    });
    if (!startRes.ok) {
      const textToParse = await startRes.text();
      let errDetail = textToParse;
      try { errDetail = JSON.parse(textToParse).detail || textToParse; } catch (e) { }
      throw new Error(errDetail);
    }
    const data = await startRes.json();

    state.totalSkills = data.total_skills;
    state.jdSkills = data.jd_skills;
    state.currentSkillIndex = 0;

    // Switch to chat view
    hide("upload-section");
    show("chat-section");
    renderSkillChips();
    updateProgress(0);
    appendBubble("ai", data.message);

    hideSpinner();
  } catch (err) {
    hideSpinner();
    showError("upload-error", "Error: " + err.message);
  }
}

/* ── Skill chips ── */
function renderSkillChips() {
  const container = $("skill-chips");
  container.innerHTML = "";
  state.jdSkills.forEach((s, i) => {
    const chip = document.createElement("span");
    chip.className = "skill-chip" + (i === 0 ? " active" : "");
    chip.id = `chip-${i}`;
    chip.textContent = s.skill;
    container.appendChild(chip);
  });
}

function updateProgress(doneCount) {
  const pct = state.totalSkills ? Math.round((doneCount / state.totalSkills) * 100) : 0;
  $("progress-bar").style.width = pct + "%";
  $("progress-label").textContent = `Skill ${doneCount} of ${state.totalSkills} assessed`;

  // Update chips
  for (let i = 0; i < state.totalSkills; i++) {
    const chip = $(`chip-${i}`);
    if (!chip) continue;
    chip.className = "skill-chip";
    if (i < doneCount) chip.classList.add("done");
    else if (i === doneCount) chip.classList.add("active");
  }
}

/* ── Chat bubble ── */
function appendBubble(role, text) {
  const box = $("chat-box");
  const div = document.createElement("div");
  div.className = `bubble ${role === "ai" ? "ai" : "user"}`;
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

/* ── Step 2: Send chat message ── */
async function sendMessage() {
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text) return;

  appendBubble("user", text);
  input.value = "";
  $("send-btn").disabled = true;

  try {
    const res = await fetch(`${API_BASE_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, message: text }),
    });
    if (!res.ok) {
      const textToParse = await res.text();
      let errDetail = textToParse;
      try { errDetail = JSON.parse(textToParse).detail || textToParse; } catch (e) { }
      throw new Error(errDetail);
    }
    const data = await res.json();

    appendBubble("ai", data.message);

    if (data.current_skill_index !== undefined) {
      updateProgress(data.current_skill_index);
    }

    if (data.phase === "complete") {
      showSpinner("Building your learning plan...");
      setTimeout(() => {
        hideSpinner();
        hide("chat-section");
        renderLearningPlan(data.learning_plan, data.assessments);
        show("plan-section");
      }, 800);
    }
  } catch (err) {
    appendBubble("ai", "Something went wrong. Please try again.");
  } finally {
    $("send-btn").disabled = false;
    $("chat-input").focus();
  }
}

/* ── Step 3: Render learning plan ── */
function renderLearningPlan(plan, assessments) {
  // Readiness ring
  const score = plan.overall_readiness_score || 0;
  $("readiness-score").textContent = score + "%";
  const circumference = 2 * Math.PI * 50; // r=50
  const fill = (score / 100) * circumference;
  setTimeout(() => {
    $("ring-fill").setAttribute("stroke-dasharray", `${fill} ${circumference}`);
  }, 100);

  // Summary
  $("readiness-summary").textContent = plan.summary || "";

  // Strengths
  const strengthsEl = $("strengths-list");
  strengthsEl.innerHTML = "";
  (plan.strengths || []).forEach((s) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = s;
    strengthsEl.appendChild(chip);
  });

  // Assessment table
  const tbody = $("assessment-body");
  tbody.innerHTML = "";
  if (assessments) {
    Object.entries(assessments).forEach(([skill, data]) => {
      const score = data.score || 0;
      const level = scoreToLevel(score);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${skill}</td>
        <td><span class="score-badge score-${score}">${score}</span></td>
        <td><span class="level-badge level-${level.toLowerCase()}">${level}</span></td>
        <td style="color:var(--muted);font-size:0.82rem">${data.reason || ""}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // Critical gaps
  const gapsList = $("gaps-list");
  gapsList.innerHTML = "";
  (plan.critical_gaps || []).forEach((gap) => {
    const card = document.createElement("div");
    card.className = "gap-card";
    const resources = (gap.resources || [])
      .map(
        (r) => `<li>
        <span class="res-type">${r.type}</span>
        <span>${r.title}${r.url_hint ? ` — <em style="color:var(--muted)">${r.url_hint}</em>` : ""}</span>
        <span class="res-time">${r.time || ""}</span>
      </li>`
      )
      .join("");

    card.innerHTML = `
      <div class="gap-card-header">
        <h4>${gap.skill}</h4>
        <div class="gap-meta">
          <span class="priority-badge priority-${gap.priority}">${gap.priority}</span>
          <span class="time-tag">~${gap.time_estimate_weeks} weeks</span>
        </div>
      </div>
      <p class="gap-path">${gap.learning_path || ""}</p>
      ${resources ? `<ul class="resources-list">${resources}</ul>` : ""}
    `;
    gapsList.appendChild(card);
  });

  // Adjacent skills
  const adjList = $("adjacent-list");
  adjList.innerHTML = "";
  (plan.adjacent_skills_to_develop || []).forEach((s) => {
    const card = document.createElement("div");
    card.className = "adjacent-card";
    card.innerHTML = `
      <div>
        <h4>${s.skill}</h4>
        <p>${s.why_valuable || ""}</p>
      </div>
      <span class="adjacent-weeks">~${s.time_estimate_weeks}w</span>
    `;
    adjList.appendChild(card);
  });

  // 30-day plan
  const planEl = $("action-plan");
  planEl.innerHTML = "";
  (plan["30_day_action_plan"] || []).forEach((action) => {
    const li = document.createElement("li");
    li.textContent = action;
    planEl.appendChild(li);
  });

  // Footer
  if (plan.total_estimated_weeks) {
    $("total-weeks").textContent = `Estimated total upskilling time: ${plan.total_estimated_weeks} weeks`;
  }
}

function scoreToLevel(score) {
  const map = { 1: "None", 2: "Beginner", 3: "Intermediate", 4: "Proficient", 5: "Expert" };
  return map[score] || "Unknown";
}

function restartApp() {
  location.reload();
}
