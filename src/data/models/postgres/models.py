from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Float, String, Text, UniqueConstraint, Index, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.models.postgres.base import Base, utc_now
from src.schemas.study_material import JobStatus, MaterialLifecycleStatus, ReviewStatus
from src.schemas.quiz import QuizSessionStatus


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    subjects: Mapped[list["Subject"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    grade_level: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    owner: Mapped["User"] = relationship(back_populates="subjects")
    concepts: Mapped[list["Concept"]] = relationship(back_populates="subject", cascade="all, delete-orphan")


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    material_status: Mapped[MaterialLifecycleStatus] = mapped_column(
        SAEnum(MaterialLifecycleStatus, name="material_lifecycle_status", native_enum=False),
        default=MaterialLifecycleStatus.unavailable,
    )
    material_version: Mapped[int] = mapped_column(Integer, default=0)

    subject: Mapped["Subject"] = relationship(back_populates="concepts")


class MaterialJob(Base):
    __tablename__ = "material_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"), index=True, nullable=False)
    learner_profile: Mapped[str | None] = mapped_column(Text, default=None)
    revision_note: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status", native_enum=False),
        default=JobStatus.queued,
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="review_status", native_enum=False),
        default=ReviewStatus.pending_review,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    artifact_index: Mapped[dict] = mapped_column(JSONB, default=dict)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    reviewer_note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    output_dir: Mapped[str | None] = mapped_column(String(200), default=None)

    concepts: Mapped[list["MaterialJobConcept"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class MaterialJobConcept(Base):
    __tablename__ = "material_job_concepts"

    job_id: Mapped[str] = mapped_column(ForeignKey("material_jobs.id"), primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(120), default="queued")
    artifact_index: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    job: Mapped["MaterialJob"] = relationship(back_populates="concepts")


class ConceptMaterial(Base):
    __tablename__ = "concept_materials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    subject_id: Mapped[str] = mapped_column(ForeignKey("subjects.id"), index=True, nullable=False)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), index=True, nullable=False)
    lifecycle_status: Mapped[MaterialLifecycleStatus] = mapped_column(
        SAEnum(MaterialLifecycleStatus, name="concept_material_status", native_enum=False),
        default=MaterialLifecycleStatus.draft,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_job_id: Mapped[str] = mapped_column(ForeignKey("material_jobs.id"), index=True, nullable=False)
    artifact_index: Mapped[dict] = mapped_column(JSONB, default=dict)
    content: Mapped[dict | None] = mapped_column(JSONB, default=None)
    content_text: Mapped[str | None] = mapped_column(Text, default=None)
    content_schema_version: Mapped[str | None] = mapped_column(String(24), default="v1")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("concept_id", "version", name="uq_concept_version"),
        Index(
            "ix_concept_materials_content_text_fts",
            text("to_tsvector('english', content_text)"),
            postgresql_using="gin",
        ),
    )


class ConceptBookmark(Base):
    __tablename__ = "concept_bookmarks"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConceptVideoFeedback(Base):
    __tablename__ = "concept_video_feedback"

    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="rejected")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    subject_id: Mapped[str | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    concept_id: Mapped[str | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    material_version: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, default=list)
    correct_option: Mapped[str] = mapped_column(Text, nullable=False)
    hints: Mapped[list] = mapped_column(JSONB, default=list)
    explanation: Mapped[str | None] = mapped_column(Text, default=None)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    subject_id: Mapped[str | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    status: Mapped[QuizSessionStatus] = mapped_column(
        SAEnum(QuizSessionStatus, name="quiz_session_status", native_enum=False),
        default=QuizSessionStatus.in_progress,
    )
    concept_ids: Mapped[list] = mapped_column(JSONB, default=list)
    question_ids: Mapped[list] = mapped_column(JSONB, default=list)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0)
    score_percent: Mapped[float | None] = mapped_column(Float, default=None)
    session_meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    report: Mapped[dict | None] = mapped_column(JSONB, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QuizResponse(Base):
    __tablename__ = "quiz_responses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    session_id: Mapped[str] = mapped_column(ForeignKey("quiz_sessions.id"), nullable=False)
    question_id: Mapped[str] = mapped_column(ForeignKey("quiz_questions.id"), nullable=False)
    concept_id: Mapped[str | None] = mapped_column(
        ForeignKey("concepts.id", ondelete="SET NULL"),
        nullable=True,
    )
    selected_option: Mapped[str | None] = mapped_column(Text, default=None)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    attempt_log: Mapped[list] = mapped_column(JSONB, default=list)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_quiz_session_question"),
    )
