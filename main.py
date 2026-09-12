"""
FastAPI backend for the Talent Intelligence platform.

Run with:
    uvicorn backend.main:app --reload --port 8000

Endpoints implement the flow:
Candidate -> Resume -> Personality -> Adaptive Interview -> Scoring
-> Role Fit -> Skill Gaps -> Report
"""
import json
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from models import (
    init_db, get_db, Candidate, Resume, InterviewSession, QA, Report
)
from role_profiles import ROLE_PROFILES, PERSONALITY_ITEMS, COMPETENCIES
from logic import (
    competency_averages, compute_role_fit, compute_skill_gaps, pick_next_competency
)
import llm

app = FastAPI(title="Talent Intelligence Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

MAX_QUESTIONS = 8


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CandidateIn(BaseModel):
    name: str
    email: str
    target_role: str


class AnswerIn(BaseModel):
    qa_id: int
    answer: str


class PersonalityIn(BaseModel):
    session_id: int
    responses: dict  # {"p1": 4, "p2": 5, ...}


# ---------------------------------------------------------------------------
# Candidate + Resume
# ---------------------------------------------------------------------------

@app.get("/roles")
def list_roles():
    return {"roles": list(ROLE_PROFILES.keys()), "competencies": COMPETENCIES}


@app.post("/candidates")
def create_candidate(payload: CandidateIn, db: Session = Depends(get_db)):
    if payload.target_role not in ROLE_PROFILES:
        raise HTTPException(400, f"Unknown target_role. Choose from {list(ROLE_PROFILES.keys())}")
    candidate = Candidate(name=payload.name, email=payload.email, target_role=payload.target_role)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return {"candidate_id": candidate.id}


@app.post("/candidates/{candidate_id}/resume")
async def upload_resume(candidate_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    candidate = db.query(Candidate).get(candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    raw_bytes = await file.read()
    if file.filename.lower().endswith(".pdf"):
        text = _extract_pdf_text(raw_bytes)
    else:
        text = raw_bytes.decode("utf-8", errors="ignore")

    extracted = llm.call_llm_json(
        llm.prompt_extract_resume(text),
        fallback=llm.mock_extract_resume(text),
    )

    resume = Resume(
        candidate_id=candidate_id,
        raw_text=text,
        extracted_skills_json=json.dumps(extracted),
    )
    db.add(resume)
    db.commit()
    return {"extracted": extracted}


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        return f"[Could not parse PDF: {e}]"


# ---------------------------------------------------------------------------
# Personality & Values (Likert self-report — no LLM needed)
# ---------------------------------------------------------------------------

@app.get("/personality/items")
def get_personality_items():
    return {"items": PERSONALITY_ITEMS}


@app.post("/sessions/{candidate_id}/start")
def start_session(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.query(Candidate).get(candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    session = InterviewSession(candidate_id=candidate_id, status="in_progress")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.id}


@app.post("/personality/submit")
def submit_personality(payload: PersonalityIn, db: Session = Depends(get_db)):
    session = db.query(InterviewSession).get(payload.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.personality_json = json.dumps(payload.responses)
    db.commit()
    return {"status": "saved", "trait_scores": _score_personality(payload.responses)}


def _score_personality(responses: dict) -> dict:
    trait_map = {item["id"]: item["trait"] for item in PERSONALITY_ITEMS}
    buckets = {}
    for item_id, val in responses.items():
        trait = trait_map.get(item_id)
        if trait:
            buckets.setdefault(trait, []).append(val)
    return {t: round(sum(v) / len(v), 2) for t, v in buckets.items()}


# ---------------------------------------------------------------------------
# Adaptive Interview
# ---------------------------------------------------------------------------

@app.get("/interview/{session_id}/next-question")
def next_question(session_id: int, db: Session = Depends(get_db)):
    session = db.query(InterviewSession).get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    candidate = session.candidate
    prior_qas = db.query(QA).filter(QA.session_id == session_id).all()
    prior_list = [
        {"competency": qa.competency, "difficulty": qa.difficulty,
         "question": qa.question, "score": qa.score}
        for qa in prior_qas
    ]

    competency, difficulty = pick_next_competency(candidate.target_role, prior_list, MAX_QUESTIONS)
    if competency is None:
        session.status = "completed"
        db.commit()
        return {"done": True, "message": "Assessment complete. Generate report."}

    generated = llm.call_llm_json(
        llm.prompt_next_question(competency, difficulty, candidate.target_role, prior_list),
        fallback=llm.mock_next_question(competency, difficulty),
    )

    qa = QA(
        session_id=session_id,
        competency=generated.get("competency", competency),
        difficulty=generated.get("difficulty", difficulty),
        question=generated.get("question", "Describe a challenging business problem you solved."),
        order_index=len(prior_qas) + 1,
    )
    db.add(qa)
    db.commit()
    db.refresh(qa)

    return {
        "done": False,
        "qa_id": qa.id,
        "competency": qa.competency,
        "difficulty": qa.difficulty,
        "question": qa.question,
        "question_number": qa.order_index,
        "max_questions": MAX_QUESTIONS,
    }


@app.post("/interview/answer")
def submit_answer(payload: AnswerIn, db: Session = Depends(get_db)):
    qa = db.query(QA).get(payload.qa_id)
    if not qa:
        raise HTTPException(404, "Question not found")

    scored = llm.call_llm_json(
        llm.prompt_score_answer(qa.question, payload.answer, qa.competency),
        fallback=llm.mock_score_answer(payload.answer),
    )

    qa.answer = payload.answer
    qa.score = float(scored.get("score", 3))
    qa.feedback = scored.get("feedback", "")
    db.commit()

    return {"score": qa.score, "feedback": qa.feedback}


# ---------------------------------------------------------------------------
# Role Fit / Skill Gaps / Report
# ---------------------------------------------------------------------------

@app.get("/sessions/{session_id}/scores")
def get_scores(session_id: int, db: Session = Depends(get_db)):
    session = db.query(InterviewSession).get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    qas = db.query(QA).filter(QA.session_id == session_id).all()
    qa_list = [{"competency": qa.competency, "score": qa.score} for qa in qas]

    avgs = competency_averages(qa_list)
    role_fit = compute_role_fit(session.candidate.target_role, avgs)
    gaps = compute_skill_gaps(session.candidate.target_role, avgs)

    return {
        "competency_averages": avgs,
        "role_fit_pct": role_fit,
        "skill_gaps": gaps,
        "target_role": session.candidate.target_role,
    }


@app.post("/sessions/{session_id}/report")
def generate_report(session_id: int, db: Session = Depends(get_db)):
    session = db.query(InterviewSession).get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    candidate = session.candidate
    qas = db.query(QA).filter(QA.session_id == session_id).all()
    qa_list = [
        {"competency": qa.competency, "question": qa.question, "answer": qa.answer,
         "score": qa.score, "feedback": qa.feedback}
        for qa in qas
    ]

    avgs = competency_averages(qa_list)
    role_fit = compute_role_fit(candidate.target_role, avgs)
    gaps = compute_skill_gaps(candidate.target_role, avgs)
    gap_names = [g["competency"] for g in gaps]

    narrative = llm.call_llm_json(
        llm.prompt_report_narrative(candidate.name, candidate.target_role, role_fit, avgs, gap_names, qa_list),
        fallback=llm.mock_report(role_fit, gap_names),
    )

    existing = db.query(Report).filter(Report.session_id == session_id).first()
    if existing:
        db.delete(existing)
        db.commit()

    report = Report(
        session_id=session_id,
        role_fit_pct=role_fit,
        skill_gaps_json=json.dumps(gaps),
        narrative_json=json.dumps(narrative),
    )
    db.add(report)
    session.status = "completed"
    db.commit()

    personality_scores = _score_personality(json.loads(session.personality_json or "{}"))

    return {
        "candidate_name": candidate.name,
        "target_role": candidate.target_role,
        "role_fit_pct": role_fit,
        "competency_averages": avgs,
        "skill_gaps": gaps,
        "personality_scores": personality_scores,
        "narrative": narrative,
        "qa_transcript": qa_list,
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "talent-intel-api"}
