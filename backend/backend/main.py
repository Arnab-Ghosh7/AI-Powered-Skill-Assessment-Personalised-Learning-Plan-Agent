import os
import json
import io
from typing import Optional
from pathlib import Path
import re
import litellm
import pdfplumber
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import ast

load_dotenv()

app = FastAPI(title="SkillSense AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Server Error: {str(exc)}"}
    )

API_KEY = os.getenv("API_KEY")
MODEL   = os.getenv("MODEL", "openrouter/meta-llama/llama-3.1-8b-instruct:free")

litellm.drop_params = True  # ignore unsupported params silently

# In-memory session store
sessions: dict[str, dict] = {}

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ─── Helper: call the model ────────────────────────────────────────────────────

def chat_complete(system: str, messages: list[dict], max_tokens: int = 1024) -> str:
    """Universal helper — works with any provider via LiteLLM."""
    full_messages = [{"role": "system", "content": system}] + messages
    response = litellm.completion(
        model=MODEL,
        messages=full_messages,
        max_tokens=max_tokens,
        api_key=API_KEY,
    )
    return response.choices[0].message.content


# ─── Models ───────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    session_id: str
    message: str


class SessionStartRequest(BaseModel):
    session_id: str
    jd_text: str
    resume_text: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)

def _parse_json_robustly(text: str, default_val=None):
    if default_val is None: default_val = []
    # 1. Try to extract from markdown code blocks
    matches = re.finditer(r'```(?:json)?\s*([\s\S]*?)```', text)
    for match in matches:
        try: return json.loads(match.group(1).strip())
        except: pass
    
    # 2. Try regex matching [ ... ] or { ... }
    match = re.search(r'(\[\s*\{.*?\}\s*\]|\{.*?\})', text, re.DOTALL)
    if match:
        try: return json.loads(match.group(1).strip())
        except Exception:
            try: return ast.literal_eval(match.group(1).strip())
            except Exception: pass
        
    # 3. Direct Parse
    try: return json.loads(text.strip())
    except Exception:
        try: return ast.literal_eval(text.strip())
        except Exception:
            return default_val


def extract_skills_from_jd(jd_text: str) -> list[dict]:
    raw = chat_complete(
        system=(
            "You are an expert technical recruiter. Extract ALL required skills from the "
            "job description. Return a JSON array only — no markdown, no explanation. "
            'Each item: {"skill": "skill name", "importance": "critical|important|nice-to-have", '
            '"category": "technical|soft|domain"}'
        ),
        messages=[{"role": "user", "content": f"Job Description:\n{jd_text}"}],
        max_tokens=1024,
    )
    return _parse_json_robustly(raw, [])


def extract_resume_skills(resume_text: str) -> list[str]:
    raw = chat_complete(
        system=(
            "Extract all skills, tools, technologies, and competencies mentioned in this resume. "
            "Return a JSON array of strings only — no markdown."
        ),
        messages=[{"role": "user", "content": f"Resume:\n{resume_text}"}],
        max_tokens=512,
    )
    return _parse_json_robustly(raw, [])


def build_assessment_system_prompt(session: dict) -> str:
    jd_skills = json.dumps(session["jd_skills"], indent=2)
    resume_skills = json.dumps(session["resume_skills"], indent=2)
    
    # Safely get current skill
    idx = session.get("current_skill_index", 0)
    skills_list = session.get("jd_skills", [])
    if not skills_list:
        current_skill = "General Evaluation"
    else:
        current_skill = skills_list[idx % len(skills_list)].get("skill", "General Skill")
        
    assessed_so_far = json.dumps(session.get("assessments", {}), indent=2)

    return f"""You are SkillSense, a friendly but rigorous technical interviewer conducting a skill assessment.

Job requires these skills:
{jd_skills}

Candidate's resume lists:
{resume_skills}

Skills assessed so far:
{assessed_so_far}

Currently assessing: **{current_skill}**

Rules:
- Ask ONE focused question at a time about the current skill.
- Questions should probe real understanding — not just "do you know X?" but practical scenarios, debugging, trade-offs.
- After the candidate answers, ask 1 follow-up if needed to clarify depth.
- After 2 questions on this skill, assign a score internally (1-5) and move on by saying exactly: "SKILL_ASSESSED:{current_skill}:SCORE:<1-5>:<one-line-reason>"
- Keep tone warm and encouraging, not interrogative.
- Never reveal the score to the candidate mid-assessment.
- If the candidate says "skip" or "I don't know this", score it 1 and move on.
- Do NOT ask about skills already assessed."""


def build_plan_prompt(session: dict) -> str:
    return f"""You are a world-class learning coach. Based on this skill assessment, create a personalised learning plan.

Job Description Skills Required:
{json.dumps(session["jd_skills"], indent=2)}

Candidate Resume Skills:
{json.dumps(session["resume_skills"], indent=2)}

Assessment Results (skill -> score 1-5, reason):
{json.dumps(session["assessments"], indent=2)}

Scoring guide: 1=no knowledge, 2=beginner, 3=intermediate, 4=proficient, 5=expert

Create a JSON learning plan with this exact structure:
{{
  "summary": "2-3 sentence personalised summary of the candidate's readiness",
  "overall_readiness_score": <0-100>,
  "strengths": ["skill1", "skill2"],
  "critical_gaps": [
    {{
      "skill": "skill name",
      "current_level": "beginner|none",
      "target_level": "proficient",
      "priority": "high|medium|low",
      "time_estimate_weeks": <number>,
      "resources": [
        {{"title": "resource name", "type": "course|book|docs|project|video", "url_hint": "platform or publisher name", "time": "X hours/weeks"}}
      ],
      "learning_path": "2-3 sentence description of how to learn this skill"
    }}
  ],
  "adjacent_skills_to_develop": [
    {{
      "skill": "skill name",
      "why_valuable": "reason it helps bridge gaps",
      "time_estimate_weeks": <number>
    }}
  ],
  "30_day_action_plan": ["action 1", "action 2", "action 3", "action 4", "action 5"],
  "total_estimated_weeks": <number>
}}

Return JSON only — no markdown fences."""


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.post("/api/upload-text")
async def upload_resume_jd(
    jd_file: Optional[UploadFile] = File(None),
    resume_file: Optional[UploadFile] = File(None),
    jd_text: str = Form(""),
    resume_text: str = Form(""),
):
    """Parse uploaded files (PDF or text) and return extracted text."""
    if jd_file and jd_file.filename:
        raw = await jd_file.read()
        if jd_file.filename.lower().endswith(".pdf"):
            jd_text = extract_text_from_pdf(raw)
        else:
            jd_text = raw.decode("utf-8", errors="replace")

    if resume_file and resume_file.filename:
        raw = await resume_file.read()
        if resume_file.filename.lower().endswith(".pdf"):
            resume_text = extract_text_from_pdf(raw)
        else:
            resume_text = raw.decode("utf-8", errors="replace")

    if not jd_text.strip() or not resume_text.strip():
        raise HTTPException(400, "Both JD and Resume are required.")

    return {"jd_text": jd_text, "resume_text": resume_text}


@app.post("/api/start-session")
async def start_session(req: SessionStartRequest):
    """Extract skills and initialise assessment session."""
    jd_skills = extract_skills_from_jd(req.jd_text)
    resume_skills = extract_resume_skills(req.resume_text)

    # Filter to critical + important skills for assessment (cap at 6 to keep it sane)
    priority_skills = [
        s for s in jd_skills if isinstance(s, dict) and s.get("importance") in ("critical", "important")
    ][:6]
    if not priority_skills:
        priority_skills = [s for s in jd_skills if isinstance(s, dict)][:6]
        
    # If LLM completely failed to extract, construct a dummy skill sequence
    if not priority_skills:
        priority_skills = [{"skill": "Python/Technical Basics", "importance": "critical", "category": "technical"}]

    session = {
        "id": req.session_id,
        "jd_text": req.jd_text,
        "resume_text": req.resume_text,
        "jd_skills": priority_skills,
        "resume_skills": resume_skills,
        "current_skill_index": 0,
        "assessments": {},
        "history": [],
        "phase": "assessment",
    }
    sessions[req.session_id] = session

    # Kick off with an intro message
    first_message = chat_complete(
        system=build_assessment_system_prompt(session),
        messages=[
            {
                "role": "user",
                "content": "Please introduce yourself briefly and start assessing the first skill.",
            }
        ],
        max_tokens=300,
    )
    session["history"].append({"role": "assistant", "content": first_message})

    return {
        "session_id": req.session_id,
        "jd_skills": priority_skills,
        "resume_skills": resume_skills,
        "message": first_message,
        "total_skills": len(priority_skills),
        "current_skill_index": 0,
    }


@app.post("/api/chat")
async def chat(msg: ChatMessage):
    """Handle a chat turn during assessment."""
    session = sessions.get(msg.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    if session["phase"] == "complete":
        return {"message": "Assessment complete. Check your learning plan.", "phase": "complete"}

    # Append user message
    session["history"].append({"role": "user", "content": msg.message})

    # Keep last 20 turns to manage context
    history = session["history"][-20:]

    assistant_text = chat_complete(
        system=build_assessment_system_prompt(session),
        messages=history,
        max_tokens=600,
    )
    session["history"].append({"role": "assistant", "content": assistant_text})

    # Check if a skill was assessed
    skill_done = False
    skill_name = None
    if "SKILL_ASSESSED:" in assistant_text:
        lines = assistant_text.split("\n")
        for line in lines:
            if line.startswith("SKILL_ASSESSED:"):
                parts = line.split(":")
                if len(parts) >= 4:
                    skill_name = parts[1]
                    score = int(parts[3]) if parts[3].isdigit() else 3
                    reason = ":".join(parts[4:]) if len(parts) > 4 else ""
                    session["assessments"][skill_name] = {
                        "score": score,
                        "reason": reason.strip(),
                    }
                    skill_done = True

        session["current_skill_index"] += 1

        if session["current_skill_index"] >= len(session["jd_skills"]):
            session["phase"] = "complete"

            # Generate the learning plan
            plan_text = chat_complete(
                system="You are a world-class learning coach. Return only valid JSON, no markdown.",
                messages=[{"role": "user", "content": build_plan_prompt(session)}],
                max_tokens=2048,
            )
            session["learning_plan"] = _parse_json_robustly(plan_text, {})

            display_text = "\n".join(
                l for l in assistant_text.split("\n") if not l.startswith("SKILL_ASSESSED:")
            ).strip()

            return {
                "message": display_text + "\n\nAll skills assessed! Generating your personalised learning plan...",
                "phase": "complete",
                "skill_assessed": skill_name,
                "assessments": session["assessments"],
                "learning_plan": session["learning_plan"],
                "current_skill_index": session["current_skill_index"],
            }

    display_text = "\n".join(
        l for l in assistant_text.split("\n") if not l.startswith("SKILL_ASSESSED:")
    ).strip()

    return {
        "message": display_text,
        "phase": "assessment",
        "skill_assessed": skill_name if skill_done else None,
        "assessments": session["assessments"],
        "current_skill_index": session["current_skill_index"],
    }


@app.get("/api/plan/{session_id}")
async def get_plan(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["phase"] != "complete":
        raise HTTPException(400, "Assessment not complete yet")
    return {
        "learning_plan": session["learning_plan"],
        "assessments": session["assessments"],
        "jd_skills": session["jd_skills"],
    }


# Serve frontend static files
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
