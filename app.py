"""
Streamlit frontend for the Talent Intelligence platform.

Run with:
    streamlit run frontend/app.py

Assumes the FastAPI backend is running at BACKEND_URL (default http://localhost:8000).
"""
import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Talent Intelligence Platform", layout="centered")

# ---------------------------------------------------------------------------
# Session state bootstrap
# ---------------------------------------------------------------------------
for key, default in [
    ("stage", "register"),
    ("candidate_id", None),
    ("session_id", None),
    ("target_role", None),
    ("current_q", None),
    ("q_count", 0),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def api(method, path, **kwargs):
    url = f"{BACKEND_URL}{path}"
    try:
        resp = requests.request(method, url, timeout=60, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot reach backend at {BACKEND_URL}. Is `uvicorn backend.main:app` running?")
        st.stop()
    except requests.exceptions.HTTPError as e:
        st.error(f"API error: {e} — {resp.text}")
        st.stop()


st.title("🧭 Talent Intelligence Platform")
st.caption("Candidate → Resume → Assessment → AI Scoring → Role Fit → Report")

stages = ["register", "resume", "personality", "interview", "report"]
st.progress((stages.index(st.session_state.stage) + 1) / len(stages))

# ---------------------------------------------------------------------------
# STAGE 1: Registration
# ---------------------------------------------------------------------------
if st.session_state.stage == "register":
    st.header("1. Candidate Registration")

    roles_data = api("GET", "/roles")
    roles = roles_data["roles"]

    with st.form("register_form"):
        name = st.text_input("Full name")
        email = st.text_input("Email")
        target_role = st.selectbox("Target role", roles)
        submitted = st.form_submit_button("Register")

    if submitted:
        if not name or not email:
            st.warning("Please fill in name and email.")
        else:
            result = api("POST", "/candidates", json={
                "name": name, "email": email, "target_role": target_role
            })
            st.session_state.candidate_id = result["candidate_id"]
            st.session_state.target_role = target_role
            st.session_state.candidate_name = name
            st.session_state.stage = "resume"
            st.rerun()

# ---------------------------------------------------------------------------
# STAGE 2: Resume upload
# ---------------------------------------------------------------------------
elif st.session_state.stage == "resume":
    st.header("2. Resume / CV Evidence")
    st.write(f"Candidate: **{st.session_state.candidate_name}** — Target role: **{st.session_state.target_role}**")

    uploaded = st.file_uploader("Upload resume (PDF or TXT)", type=["pdf", "txt"])
    skip = st.button("Skip resume upload (demo mode)")

    if uploaded is not None:
        with st.spinner("Extracting skills with AI..."):
            files = {"file": (uploaded.name, uploaded.getvalue())}
            result = api("POST", f"/candidates/{st.session_state.candidate_id}/resume", files=files)
        st.success("Resume processed.")
        st.json(result["extracted"])
        if st.button("Continue →"):
            st.session_state.stage = "personality"
            st.rerun()

    if skip:
        st.session_state.stage = "personality"
        st.rerun()

# ---------------------------------------------------------------------------
# STAGE 3: Personality & Values (Likert)
# ---------------------------------------------------------------------------
elif st.session_state.stage == "personality":
    st.header("3. Personality & Values Assessment")

    if st.session_state.session_id is None:
        result = api("POST", f"/sessions/{st.session_state.candidate_id}/start")
        st.session_state.session_id = result["session_id"]

    items_data = api("GET", "/personality/items")
    items = items_data["items"]

    st.write("Rate your agreement (1 = Strongly Disagree, 5 = Strongly Agree)")
    responses = {}
    with st.form("personality_form"):
        for item in items:
            responses[item["id"]] = st.slider(item["text"], 1, 5, 3, key=item["id"])
        submitted = st.form_submit_button("Submit & Continue →")

    if submitted:
        api("POST", "/personality/submit", json={
            "session_id": st.session_state.session_id,
            "responses": responses,
        })
        st.session_state.stage = "interview"
        st.rerun()

# ---------------------------------------------------------------------------
# STAGE 4: Adaptive Interview (scenario / case / written)
# ---------------------------------------------------------------------------
elif st.session_state.stage == "interview":
    st.header("4. Adaptive Consulting Case Interview")
    st.caption("Questions adapt in real time based on your competency scores so far.")

    if st.session_state.current_q is None:
        with st.spinner("Generating your next question..."):
            q = api("GET", f"/interview/{st.session_state.session_id}/next-question")
        st.session_state.current_q = q

    q = st.session_state.current_q

    if q.get("done"):
        st.success("Assessment complete! Generating your report...")
        st.session_state.stage = "report"
        st.rerun()
    else:
        st.progress(q["question_number"] / q["max_questions"])
        st.markdown(f"**Question {q['question_number']} / {q['max_questions']}**  "
                    f"&nbsp; `{q['competency']}` &nbsp; · &nbsp; difficulty: `{q['difficulty']}`")
        st.markdown(f"### {q['question']}")

        answer = st.text_area("Your answer", height=200, key=f"answer_{q['qa_id']}")

        if st.button("Submit Answer"):
            if not answer.strip():
                st.warning("Please write an answer before submitting.")
            else:
                with st.spinner("AI is scoring your response..."):
                    result = api("POST", "/interview/answer", json={
                        "qa_id": q["qa_id"], "answer": answer
                    })
                st.info(f"Score: {result['score']}/5 — {result['feedback']}")
                st.session_state.current_q = None
                st.session_state.q_count += 1
                if st.button("Next Question →"):
                    st.rerun()
                st.stop()

# ---------------------------------------------------------------------------
# STAGE 5: Report
# ---------------------------------------------------------------------------
elif st.session_state.stage == "report":
    st.header("5. Candidate Assessment Report")

    with st.spinner("Compiling AI-generated report..."):
        report = api("POST", f"/sessions/{st.session_state.session_id}/report")

    col1, col2 = st.columns(2)
    col1.metric("Role Fit", f"{report['role_fit_pct']}%")
    col2.metric("Target Role", report["target_role"])

    st.subheader("Competency Scores")
    st.bar_chart(report["competency_averages"])

    st.subheader("Summary")
    st.write(report["narrative"].get("summary", ""))

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("💪 Strengths")
        for s in report["narrative"].get("strengths", []):
            st.markdown(f"- {s}")
    with c2:
        st.subheader("🎯 Skill Gaps")
        if report["skill_gaps"]:
            for g in report["skill_gaps"]:
                st.markdown(f"- **{g['competency']}**: {g['current']}/5 (needs {g['required']}/5)")
        else:
            st.markdown("- No significant gaps identified")

    st.subheader("📚 Personalized Learning Plan")
    for item in report["narrative"].get("learning_plan", []):
        st.markdown(f"- **{item.get('competency','')}**: {item.get('action','')} _(via {item.get('resource','')})_")

    st.subheader("🧠 Personality & Values Signal")
    st.json(report["personality_scores"])

    with st.expander("Full interview transcript"):
        for qa in report["qa_transcript"]:
            st.markdown(f"**[{qa['competency']}] {qa['question']}**")
            st.write(qa["answer"])
            st.caption(f"Score: {qa['score']}/5 — {qa['feedback']}")
            st.divider()

    if st.button("🔄 Start New Assessment"):
        for key in ["stage", "candidate_id", "session_id", "target_role", "current_q", "q_count"]:
            st.session_state[key] = None
        st.session_state.stage = "register"
        st.rerun()
