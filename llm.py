"""
Single LLM entrypoint used for every AI step:
  - resume skill extraction
  - adaptive question generation
  - answer scoring
  - report narrative generation

Uses LangChain's HuggingFaceEndpoint against the HF Inference API.
Falls back to deterministic mock responses if HF_TOKEN is missing or the
call fails -- keeps your demo alive even with flaky wifi/rate limits.
"""
import os
import json
import re
import random
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
# from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("HF_TOKEN")
model = os.getenv("HF_MODEL")

# llm = HuggingFaceEndpoint(
#     repo_id=model,
#     huggingfacehub_api_token=token,
#     task="text-generation",
#     max_new_tokens=100,
#     temperature=0.7,
# )
# chat_model = ChatHuggingFace(llm=llm)


# response = chat_model.invoke("Say hello and tell me that you are working.")

# print(response.content)
_llm = None


def get_llm():
   
    global _llm
    if _llm is not None:
        return _llm
    if not token:
        return None
    try:
        
        _llm = HuggingFaceEndpoint(
            repo_id=model,
            huggingfacehub_api_token=token,
            task="conversational",
            max_new_tokens=600,
            temperature=0.6,
            top_p=0.9,
        )
        _llm = ChatHuggingFace(llm=_llm)
        return _llm
    except Exception as e:
        print(f"[llm] failed to init HF endpoint: {e}")
        return None

def _extract_json(text: str):
    """Pull the first {...} or [...] block out of an LLM response and parse it."""
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in LLM output: {text[:200]}")
    return json.loads(match.group(1))


def call_llm_json(prompt: str, fallback: dict):
    """
    Calls the LLM with a prompt that demands JSON-only output.
    On any failure (no token, network, bad parse), returns `fallback`
    so the demo never hard-crashes.
    """
    llm = get_llm()
    if llm is None:
        return fallback
    try:
        response = llm.invoke(prompt)
        raw = response.content
        return _extract_json(raw)
    except Exception as e:
        print(f"[llm] call failed, using fallback: {e}")
        return fallback
# print(call_llm_json("Hello, return JSON: {\"greeting\": \"hi\"}", {"greeting": "fallback"}))

# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def prompt_extract_resume(resume_text: str) -> str:
    return f"""You are a resume parser for a management consulting recruiting platform.
Return ONLY valid JSON, no preamble, no markdown fences.

Extract from the resume text below:
- "skills": list of hard/soft skills (max 15)
- "years_exp": estimated total years of professional experience (integer)
- "summary": 2-sentence professional summary
- "signals": object mapping each of these competencies to "low"/"medium"/"high"
  based on resume evidence only: ["Problem Solving","Business Acumen","Communication","Leadership","Data & Quant Reasoning"]

Resume text:
\"\"\"{resume_text[:4000]}\"\"\"

JSON:"""


def prompt_next_question(competency: str, difficulty: str, target_role: str, prior_qas: list) -> str:
    history = "\n".join(
        f"- [{qa['competency']}/{qa['difficulty']}] Q: {qa['question'][:150]} | Score: {qa.get('score','?')}"
        for qa in prior_qas
    ) or "None yet."

    return f"""You are a case-interview designer for a management consulting assessment platform.
Target role: {target_role}
Generate ONE adaptive scenario/case-style question targeting the competency "{competency}"
at "{difficulty}" difficulty. Base it on realistic consulting scenarios (market entry,
profitability decline, M&A due diligence, operational turnaround, pricing strategy, etc).
Do not repeat themes already covered below.

Prior questions asked:
{history}

Return ONLY valid JSON:
{{"question": "...", "competency": "{competency}", "difficulty": "{difficulty}"}}

JSON:"""


def prompt_score_answer(question: str, answer: str, competency: str) -> str:
    return f"""You are an expert management-consulting interview assessor.
Score the candidate's answer on a 1-5 scale for the competency "{competency}" using this rubric:
1 = No structure, no insight. 2 = Weak structure, surface-level.
3 = Adequate structure, some insight. 4 = Strong structure, clear insight, minor gaps.
5 = MBB-caliber: structured, quantified, actionable, insightful.

Question: {question}
Candidate answer: \"\"\"{answer[:3000]}\"\"\"

Return ONLY valid JSON:
{{"score": <1-5 integer>, "feedback": "<2 sentence specific feedback>"}}

JSON:"""


def prompt_report_narrative(candidate_name: str, target_role: str, role_fit_pct: float,
                             competency_scores: dict, skill_gaps: list, qas: list) -> str:
    qa_summary = "\n".join(
        f"- {qa['competency']}: score {qa.get('score','?')}/5 — {qa.get('feedback','')}"
        for qa in qas
    )
    return f"""You are writing a candidate assessment report for a management consulting
talent platform. Be direct, specific, and professional -- like a real assessor's writeup.

Candidate: {candidate_name}
Target role: {target_role}
Overall role fit: {role_fit_pct:.1f}%
Competency scores: {json.dumps(competency_scores)}
Skill gaps (below role bar): {skill_gaps}

Interview performance detail:
{qa_summary}

Return ONLY valid JSON with these keys:
{{
  "summary": "<3-4 sentence overall assessment>",
  "strengths": ["<bullet>", "<bullet>", "<bullet>"],
  "gaps": ["<bullet>", "<bullet>"],
  "learning_plan": [
    {{"competency": "...", "action": "specific development action", "resource": "suggested resource/format"}}
  ]
}}

JSON:"""


# ---------------------------------------------------------------------------
# Deterministic fallbacks (used if no HF_TOKEN / call fails) so the demo
# never breaks even without a working model endpoint.
# ---------------------------------------------------------------------------

_MOCK_QUESTIONS = {
    "Problem Solving": "A client's revenue has declined 15% YoY despite stable market demand. How would you structure your investigation?",
    "Business Acumen": "A retail client wants to enter a new international market. What factors would you assess before recommending entry?",
    "Communication": "How would you explain a complex cost-reduction recommendation to a skeptical, non-technical CEO in under 2 minutes?",
    "Leadership": "A junior team member on your case team is consistently missing deadlines. How do you handle this mid-engagement?",
    "Data & Quant Reasoning": "A client's profitability dropped despite rising sales. Walk through how you'd break down the profitability equation to find the cause.",
}


def mock_next_question(competency: str, difficulty: str) -> dict:
    return {
        "question": _MOCK_QUESTIONS.get(competency, "Describe a time you solved an ambiguous business problem."),
        "competency": competency,
        "difficulty": difficulty,
    }


def mock_score_answer(answer: str) -> dict:
    # crude heuristic so the mock isn't static: longer, more structured answers score higher
    length_score = min(len(answer.split()) / 40, 1.0)
    structure_bonus = 1 if any(k in answer.lower() for k in ["first", "second", "framework", "because", "therefore"]) else 0
    score = round(2 + 2 * length_score + 0.5 * structure_bonus + random.uniform(-0.3, 0.3))
    score = max(1, min(5, score))
    return {"score": score, "feedback": "Mock scoring active (no HF_TOKEN set) -- structure and depth were the main signals used."}


def mock_extract_resume(resume_text: str) -> dict:
    return {
        "skills": ["Excel", "Financial Modeling", "Stakeholder Management", "Market Research"],
        "years_exp": 3,
        "summary": "Experienced analyst with cross-functional project exposure.",
        "signals": {
            "Problem Solving": "medium",
            "Business Acumen": "medium",
            "Communication": "medium",
            "Leadership": "low",
            "Data & Quant Reasoning": "medium",
        },
    }


def mock_report(role_fit_pct: float, skill_gaps: list) -> dict:
    return {
        "summary": f"Candidate demonstrates solid consulting fundamentals with an overall role fit of {role_fit_pct:.0f}%. Performance was consistent across structured problem-solving tasks with room to grow in leadership scenarios.",
        "strengths": ["Clear structured thinking", "Good quantitative reasoning", "Client-oriented framing"],
        "gaps": skill_gaps or ["No major gaps identified"],
        "learning_plan": [
            {"competency": g, "action": f"Targeted case practice focused on {g}", "resource": "Casebook + mock interview partner"}
            for g in (skill_gaps or ["Leadership"])
        ],
    }
