# modus_ai_agent


# Talent Intelligence Platform (Hackathon Build)







Candidate → Resume → Personality → Adaptive AI Interview → Scoring → Role Fit → Skill Gaps → Report

## Stack
- **Frontend**: Streamlit
- **Backend**: FastAPI + SQLite
- **AI**: LangChain + HuggingFace Inference API (single model does extraction, question generation, scoring, and report writing)

## Setup (5 minutes)

```bash
cd talent-intel
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set HF_TOKEN (get one free at https://huggingface.co/settings/tokens)
# and HF_MODEL_REPO to any instruct model served on the HF Inference API
```

**No HF_TOKEN? No problem.** The backend automatically falls back to deterministic
mock responses for every AI step (extraction, question gen, scoring, report) so the
full flow still runs end-to-end for a demo — it just won't be real AI output.

## Run

Two terminals:

```bash
# Terminal 1 — backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
streamlit run frontend/app.py
```

Open the Streamlit URL it prints (usually http://localhost:8501).

## What's implemented

| Flow step | How |
|---|---|
| Candidate registration | `POST /candidates` |
| Resume/CV evidence | `POST /candidates/{id}/resume` — PDF/TXT parsed, LLM extracts skills + competency signals |
| Personality & Values | 10-item Likert self-report, scored deterministically (no LLM needed) |
| Scenario / case / written assessment | Adaptive loop: `GET /interview/{session}/next-question` picks the weakest/unexplored competency and generates a case question; `POST /interview/answer` scores it 1-5 with feedback |
| AI-based scoring | LLM rubric scoring per answer, stored per QA row |
| Competency/role matching | `logic.compute_role_fit()` — ratio of candidate score to role's required bar per competency |
| Skills-gap identification | `logic.compute_skill_gaps()` — any competency below the role's required level |
| Personalized learning plan | Generated inside the final report narrative |
| Candidate report | `POST /sessions/{id}/report` — full JSON: summary, strengths, gaps, learning plan, transcript |

## Adaptive logic (the core differentiator)

Each `next-question` call:
1. Looks at every competency required for the target role.
2. If any competency hasn't been asked yet, asks it first (prioritizing by role importance).
3. Once all are covered, it re-targets whichever competency has the **lowest average score**,
   and adjusts difficulty (`easy` / `medium` / `hard`) based on how that competency is trending.
4. Hard-stops at 8 questions so demo timing is predictable.

## Customizing roles / competencies

Edit `backend/role_profiles.py` — `ROLE_PROFILES` maps role name → required competency levels (1-5).
Add a role or competency there and it propagates through role-fit, gap analysis, and question generation
automatically.

## Known shortcuts (by design, for a 3-hour build)

- SQLite, not Postgres — fine for a demo, swap `DATABASE_URL` in `models.py` for production.
- One shared LLM call for extraction/question-gen/scoring/report — a production system would use
  separate fine-tuned or smaller models per task for cost/latency.
- No auth — add an auth layer before any real deployment.
- Personality assessment is self-report only, not a validated psychometric instrument.
