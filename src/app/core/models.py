from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Candidate(Base):
    __tablename__ = "candidates"

    candidate_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[Optional[str]] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String, index=True)
    anchor_object_id: Mapped[str] = mapped_column(String, index=True)
    anchor_object_type: Mapped[str] = mapped_column(String, index=True)
    base_conf: Mapped[float] = mapped_column(Float, default=0.0)
    final_conf: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    priority_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    evidence: Mapped["CandidateEvidence"] = relationship(
        "CandidateEvidence", back_populates="candidate", uselist=False
    )
    labels: Mapped[list["Label"]] = relationship("Label", back_populates="candidate")
    llm_results: Mapped[list["LLMResult"]] = relationship("LLMResult", back_populates="candidate")


class CandidateEvidence(Base):
    __tablename__ = "candidate_evidence"

    candidate_id: Mapped[str] = mapped_column(
        String, ForeignKey("candidates.candidate_id"), primary_key=True
    )
    evidence_event_ids: Mapped[Optional[Any]] = mapped_column(JSON)
    evidence_object_ids: Mapped[Optional[Any]] = mapped_column(JSON)
    timeline: Mapped[Optional[Any]] = mapped_column(JSON)
    features: Mapped[Optional[Any]] = mapped_column(JSON)
    subgraph: Mapped[Optional[Any]] = mapped_column(JSON)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="evidence")


class LLMResult(Base):
    __tablename__ = "llm_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_id: Mapped[str] = mapped_column(String, ForeignKey("candidates.candidate_id"))
    model: Mapped[Optional[str]] = mapped_column(String)
    provider: Mapped[Optional[str]] = mapped_column(String)
    schema_version: Mapped[Optional[str]] = mapped_column(String)
    prompt_hash: Mapped[Optional[str]] = mapped_column(String)
    input_hash: Mapped[Optional[str]] = mapped_column(String)
    verdict: Mapped[Optional[str]] = mapped_column(String)
    v_conf: Mapped[Optional[float]] = mapped_column(Float)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    possible_false_positive: Mapped[Optional[Any]] = mapped_column(JSON)
    next_questions: Mapped[Optional[Any]] = mapped_column(JSON)
    raw_json: Mapped[Optional[Any]] = mapped_column(JSON)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="llm_results")


class Label(Base):
    __tablename__ = "labels"

    label_id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String, ForeignKey("candidates.candidate_id"))
    label: Mapped[str] = mapped_column(String, index=True)
    reason_code: Mapped[Optional[str]] = mapped_column(String)
    note: Mapped[Optional[str]] = mapped_column(Text)
    reviewer: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    candidate: Mapped["Candidate"] = relationship("Candidate", back_populates="labels")
