"""
SQLite models for the Talent Intelligence platform.
Kept intentionally flat/minimal for a 3-hour build.
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, ForeignKey, DateTime
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./talent_intel.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    target_role = Column(String, nullable=False)  # must match a key in ROLE_PROFILES
    created_at = Column(DateTime, default=datetime.utcnow)

    resume = relationship("Resume", back_populates="candidate", uselist=False)
    sessions = relationship("InterviewSession", back_populates="candidate")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    raw_text = Column(Text)
    extracted_skills_json = Column(Text)  # JSON string: {"skills": [...], "years_exp": n, "summary": "..."}

    candidate = relationship("Candidate", back_populates="resume")


class InterviewSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"))
    status = Column(String, default="in_progress")  # in_progress | completed
    personality_json = Column(Text, default="{}")   # Likert self-report answers
    created_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="sessions")
    qas = relationship("QA", back_populates="session")
    report = relationship("Report", back_populates="session", uselist=False)


class QA(Base):
    __tablename__ = "qas"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    competency = Column(String)
    difficulty = Column(String, default="medium")  # easy | medium | hard
    question = Column(Text)
    answer = Column(Text, nullable=True)
    score = Column(Float, nullable=True)       # 1-5
    feedback = Column(Text, nullable=True)
    order_index = Column(Integer, default=0)

    session = relationship("InterviewSession", back_populates="qas")


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    role_fit_pct = Column(Float)
    skill_gaps_json = Column(Text)   # JSON list
    narrative_json = Column(Text)    # JSON: {summary, strengths, gaps, learning_plan}
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("InterviewSession", back_populates="report")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
