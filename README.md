# SkillSense AI


## What it does

Drop in a job description and a resume. SkillSense pulls out the skills the role needs, cross-references them against the resume, then runs a short conversational assessment — scenario-based questions, not multiple choice. Each skill gets scored 1-5 based on how the conversation goes. After that, it generates a personalised learning plan: specific gaps, curated resources, time estimates.

No login, runs in the browser.

---

## Demo

Sample inputs are in `/samples`: a Senior ML Engineer JD and a mid-level data scientist resume. Load them, run through the questions, and you'll have a full plan in a few minutes.

---

## Local setup

You need Python 3.9+, pip, and an API key (e.g. Google Gemini or Groq).

```bash
git clone https://github.com/Arnab-Ghosh7/AI-Powered-Skill-Assessment-Personalised-Learning-Plan-Agent
cd skillsense-ai

cp .env .env  # Or update the provided .env with your own keys
# put your API_KEY and MODEL in .env

./start.sh        # Mac / Linux
start.bat         # Windows
```

Open `http://localhost:8000`. Dependencies install on first run.

---

## Architecture

```
Browser (Vanilla JS)
       │
       ▼
FastAPI backend (Python)
       │
       ├─ /api/upload-text   — PDF/text parsing via pdfplumber
       ├─ /api/start-session — skill extraction from JD + resume
       └─ /api/chat          — multi-turn assessment loop
                │
                ▼
          LiteLLM Router
          (Google Gemini)
```

### How scoring works

Each skill gets two questions in conversation. The AI scores internally on 1-5:

| Score | Level | What it means |
|-------|-------|---------------|
| 1 | None | No evidence of knowledge |
| 2 | Beginner | Knows it exists, little hands-on experience |
| 3 | Intermediate | Can work with guidance |
| 4 | Proficient | Works independently |
| 5 | Expert | Deep enough to teach it |

The overall readiness score (0-100) weights critical skills more. Anything at 3 or below on a required skill feeds into the gap list.

### How the learning plan is built

Gaps are sorted by how important the skill is in the JD, how far the candidate is from the required level, and whether they already know adjacent skills (which shortens the path). Resources come from the AI for that specific skill and level, not a generic list.

---

## Project structure

```
├── backend/
│   ├── main.py           — FastAPI app, all routes and agent logic
│   └── requirements.txt
├── frontend/
│   ├── index.html        — single-page app
│   ├── style.css
│   └── app.js
├── samples/
│   ├── sample_jd.txt     — Senior ML Engineer job description
│   └── sample_resume.txt — mid-level data scientist resume
├── .env.example
├── start.bat             — Windows launcher
├── start.sh              — Mac/Linux launcher
└── README.md
```

---

## Tech stack

- **Backend:** Python, FastAPI, LiteLLM
- **AI model:** Google Gemini (`gemini-2.5-flash`) via LiteLLM
- **PDF parsing:** pdfplumber
- **Frontend:** Vanilla HTML/CSS/JS, no build step

---

## Sample output

Running the sample resume against the ML Engineer JD gives roughly:

- Readiness: ~38/100
- Strengths: Python, SQL, basic statistics
- Gaps: MLOps (Docker/K8s, pipelines), PyTorch/TensorFlow, cloud ML platforms
- Estimate: 14-18 weeks to close the critical gaps, starting with MLOps and deep learning basics
- 30-day plan with concrete week-by-week steps

---

## Submission

Built for the Deccan AI Catalyst Hackathon, April 2026.

**Author:** Arnab Ghosh
