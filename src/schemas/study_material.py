from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.schemas.learning_bot import LearningBotSessionStatus
from src.schemas.quiz import QuizSessionStatus, QuizSessionType, QuizTopicPerformance


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ReviewStatus(str, Enum):
    pending_review = "pending_review"
    approved = "approved"


class MaterialLifecycleStatus(str, Enum):
    unavailable = "unavailable"
    draft = "draft"
    approved = "approved"
    published = "published"


class ConceptCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=600)
    topic_order: int = Field(ge=1, le=500)
    pass_percentage: int = Field(ge=1, le=100)


class ConceptBulkCreate(BaseModel):
    concepts: list[ConceptCreate] = Field(min_length=1, max_length=50)


class AdminConceptPlanItem(BaseModel):
    concept_id: str | None = None
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=600)
    pass_percentage: int = Field(ge=1, le=100)


class AdminConceptPlanUpdateRequest(BaseModel):
    concepts: list[AdminConceptPlanItem] = Field(min_length=1, max_length=50)


class SubjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    grade_level: str = Field(min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=600)


class AdminMaterialJobCreate(BaseModel):
    subject_id: str
    concept_ids: list[str] = Field(min_length=1, max_length=30)
    learner_profile: str | None = Field(default=None, max_length=500)


class AdminMaterialRegenerateRequest(BaseModel):
    learner_profile: str | None = Field(default=None, max_length=500)
    revision_note: str | None = Field(default=None, max_length=500)


class AdminMaterialApproveRequest(BaseModel):
    concept_ids: list[str] | None = Field(default=None, max_length=30)
    approval_note: str | None = Field(default=None, max_length=500)


class AdminMaterialPublishRequest(BaseModel):
    concept_ids: list[str] = Field(min_length=1, max_length=30)


class StudentConceptSelection(BaseModel):
    concept_ids: list[str] = Field(min_length=1, max_length=30)


class ArtifactIndex(BaseModel):
    pdf: str | None = None
    quick_revision_pdf: str | None = None
    quiz_json: str | None = None
    flashcards_json: str | None = None
    resources_json: str | None = None
    study_material_json: str | None = None
    zip: str | None = None
    extras: dict[str, str] = Field(default_factory=dict)


class ConceptMaterialResponse(BaseModel):
    concept_id: str
    concept_name: str
    lifecycle_status: MaterialLifecycleStatus
    version: int
    source_job_id: str
    artifact_index: ArtifactIndex
    generated_at: datetime
    approved_at: datetime | None = None
    published_at: datetime | None = None


class LearningSection(BaseModel):
    id: str
    title: str
    level: int = Field(ge=1, le=3)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    children: list["LearningSection"] = Field(default_factory=list)


class LearningContent(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)
    sections: list[LearningSection] = Field(default_factory=list)


class LearningContentResponse(BaseModel):
    concept_id: str
    concept_name: str
    subject_id: str
    subject_name: str
    grade_level: str
    lifecycle_status: MaterialLifecycleStatus
    version: int
    generated_at: datetime
    approved_at: datetime | None = None
    published_at: datetime | None = None
    content_schema_version: str | None = None
    content: LearningContent


class LearningContentUpdate(BaseModel):
    content: LearningContent


class StudentTopicProgressState(str, Enum):
    locked = "locked"
    available = "available"
    ready_for_assessment = "ready_for_assessment"
    retry_required = "retry_required"
    passed = "passed"


class ConceptResponse(BaseModel):
    concept_id: str
    name: str
    description: str | None = None
    topic_order: int
    pass_percentage: int
    created_at: datetime
    material_status: MaterialLifecycleStatus = MaterialLifecycleStatus.unavailable
    material_version: int = 0


class SubjectResponse(BaseModel):
    subject_id: str
    name: str
    grade_level: str
    description: str | None = None
    published: bool
    is_enrolled: bool = False
    enrolled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    concepts: list[ConceptResponse] = Field(default_factory=list)


class SubjectEnrollmentResponse(BaseModel):
    subject_id: str
    student_id: str
    enrolled_at: datetime


class StudentTopicProgressResponse(BaseModel):
    concept_id: str
    name: str
    description: str | None = None
    topic_order: int
    pass_percentage: int
    material_status: MaterialLifecycleStatus
    material_version: int = 0
    state: StudentTopicProgressState
    is_current: bool = False
    is_locked: bool = False
    learning_completed_at: datetime | None = None
    passed_at: datetime | None = None
    latest_score_percent: float | None = None
    best_score_percent: float | None = None
    assessment_attempts: int = 0
    blocker_message: str | None = None


class StudentSubjectProgressResponse(BaseModel):
    subject_id: str
    subject_name: str
    grade_level: str
    total_topics: int = 0
    completed_topics: int = 0
    progress_percent: float = 0
    current_concept_id: str | None = None
    current_concept_name: str | None = None
    topics: list[StudentTopicProgressResponse] = Field(default_factory=list)


class MaterialJobStatusResponse(BaseModel):
    job_id: str
    subject_id: str
    concept_ids: list[str]
    status: JobStatus
    review_status: ReviewStatus
    progress: int = Field(ge=0, le=100)
    concept_statuses: dict[str, str] = Field(default_factory=dict)
    artifact_index: ArtifactIndex = Field(default_factory=ArtifactIndex)
    concept_artifacts: dict[str, ArtifactIndex] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    reviewer_note: str | None = None
    created_at: datetime
    updated_at: datetime


class ConceptContentPack(BaseModel):
    concept_id: str
    concept_name: str
    definition: str
    intuition: str
    formulas: list[str] = Field(default_factory=list)
    key_steps: list[str]
    common_mistakes: list[str]
    examples: list[str]
    mcqs: list[dict[str, Any]]
    flashcards: list[dict[str, str]]
    references: list[dict[str, str]]
    recap: list[str]
    practical_examples_required: bool = True


class ConceptMaterialRecord(BaseModel):
    concept_id: str
    concept_name: str
    lifecycle_status: MaterialLifecycleStatus = MaterialLifecycleStatus.draft
    version: int = 1
    source_job_id: str
    artifact_index: ArtifactIndex = Field(default_factory=ArtifactIndex)
    generated_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    published_at: datetime | None = None


class ConceptBookmarkResponse(BaseModel):
    concept_id: str
    concept_name: str
    subject_id: str
    subject_name: str
    created_at: datetime


class FlashcardKind(str, Enum):
    core = "core"
    intuition = "intuition"
    step = "step"
    formula = "formula"
    pitfall = "pitfall"
    summary = "summary"
    practice = "practice"
    concept = "concept"


class FlashcardItem(BaseModel):
    question: str
    answer: str
    hint: str | None = None
    kind: FlashcardKind = FlashcardKind.concept


class ResourceItem(BaseModel):
    title: str
    url: str
    note: str | None = None


class ConceptResourcesResponse(BaseModel):
    concept_id: str
    concept_name: str
    subject_id: str
    subject_name: str
    resources: list[ResourceItem] = Field(default_factory=list)
    approved_video_id: str | None = None


class StudentActivityOverviewResponse(BaseModel):
    total_concepts: int = 0
    engaged_concepts: int = 0
    completed_topics: int = 0
    progress_percent: float = 0
    current_topic_name: str | None = None
    current_topic_order: int | None = None
    failed_assessments: int = 0
    passed_assessments: int = 0
    bookmarks_count: int = 0
    total_quiz_sessions: int = 0
    completed_quizzes: int = 0
    average_quiz_accuracy: float | None = None
    best_quiz_accuracy: float | None = None
    learning_sessions: int = 0
    learning_messages: int = 0
    last_activity_at: datetime | None = None


class AdminEnrolledStudentResponse(BaseModel):
    student_id: str
    student_email: str
    enrolled_at: datetime
    overview: StudentActivityOverviewResponse


class AdminStudentConceptActivityResponse(BaseModel):
    concept_id: str
    concept_name: str
    topic_order: int
    pass_percentage: int
    status: str
    progress_state: StudentTopicProgressState | None = None
    is_current: bool = False
    has_bookmark: bool = False
    learning_completed_at: datetime | None = None
    assessment_attempts: int = 0
    latest_score_percent: float | None = None
    best_score_percent: float | None = None
    passed_at: datetime | None = None
    blocker_message: str | None = None
    quiz_sessions: int = 0
    completed_quizzes: int = 0
    best_quiz_accuracy: float | None = None
    learning_sessions: int = 0
    learning_messages: int = 0
    last_activity_at: datetime | None = None


class AdminStudentQuizReportResponse(BaseModel):
    session_id: str
    session_type: QuizSessionType = QuizSessionType.custom_practice
    status: QuizSessionStatus
    started_at: datetime
    completed_at: datetime | None = None
    accuracy: float | None = None
    score_percent: float | None = None
    correct_count: int = 0
    total_questions: int = 0
    required_pass_percentage: int | None = None
    passed: bool | None = None
    topics: list[QuizTopicPerformance] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AdminStudentLearningSessionResponse(BaseModel):
    session_id: str
    concept_id: str
    concept_name: str
    status: LearningBotSessionStatus
    title: str | None = None
    prompt_count: int = 0
    message_count: int = 0
    last_message_at: datetime


class StudentActivityEventResponse(BaseModel):
    event_type: str
    title: str
    description: str | None = None
    occurred_at: datetime
    concept_id: str | None = None
    concept_name: str | None = None


class AdminStudentActivityResponse(BaseModel):
    subject_id: str
    subject_name: str
    grade_level: str
    student_id: str
    student_email: str
    enrolled_at: datetime
    overview: StudentActivityOverviewResponse
    concept_activity: list[AdminStudentConceptActivityResponse] = Field(default_factory=list)
    bookmarks: list[ConceptBookmarkResponse] = Field(default_factory=list)
    learning_sessions: list[AdminStudentLearningSessionResponse] = Field(default_factory=list)
    quiz_reports: list[AdminStudentQuizReportResponse] = Field(default_factory=list)
    recent_activity: list[StudentActivityEventResponse] = Field(default_factory=list)


class VideoFeedbackRequest(BaseModel):
    url: str


LearningSection.model_rebuild()


class SubjectRecord(BaseModel):
    subject_id: str
    name: str
    grade_level: str
    description: str | None = None
    published: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    concept_meta: dict[str, ConceptResponse] = Field(default_factory=dict)
    materials: dict[str, ConceptMaterialRecord] = Field(default_factory=dict)


class JobRecord(BaseModel):
    job_id: str = Field(default_factory=lambda: uuid4().hex)
    subject_id: str
    concept_ids: list[str]
    learner_profile: str | None = None
    revision_note: str | None = None
    status: JobStatus = JobStatus.queued
    review_status: ReviewStatus = ReviewStatus.pending_review
    progress: int = 0
    concept_statuses: dict[str, str] = Field(default_factory=dict)
    artifact_index: ArtifactIndex = Field(default_factory=ArtifactIndex)
    concept_artifacts: dict[str, ArtifactIndex] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    reviewer_note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None
    output_dir: str | None = None

    def touch(self) -> None:
        self.updated_at = utc_now()
