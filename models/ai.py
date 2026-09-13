"""Typed contracts for the bounded Advanced AI layer."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class AITaskType(StrEnum):
    LEARNING_ASSIST = "LEARNING_ASSIST"
    STUDY_PLAN = "STUDY_PLAN"
    PROGRESS_ANALYSIS = "PROGRESS_ANALYSIS"
    WEAK_AREA_ANALYSIS = "WEAK_AREA_ANALYSIS"
    TEST_PREPARATION = "TEST_PREPARATION"
    INTERVIEW_COACHING = "INTERVIEW_COACHING"
    CAREER_GUIDANCE = "CAREER_GUIDANCE"
    ROUTINE_ANALYSIS = "ROUTINE_ANALYSIS"
    DAILY_PLAN = "DAILY_PLAN"
    GENERAL_ACADEMIC_ASSIST = "GENERAL_ACADEMIC_ASSIST"


class AITaskStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class ProposalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AITask:
    task_id: str
    user_id: str
    task_type: AITaskType
    status: AITaskStatus
    agent_id: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_summary: str = ""
    output_summary: str = ""
    context_references: dict[str, Any] = field(default_factory=dict)
    provider_reference: str = ""
    action_references: tuple[str, ...] = ()
    error_category: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class AIActionProposal:
    proposal_id: str
    task_id: str
    user_id: str
    agent_id: str
    action_type: str
    target_reference: str
    summary: str
    structured_payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    status: ProposalStatus
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    error_category: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class AIAuditEvent:
    audit_id: str
    task_id: str
    user_id: str
    agent_id: str
    operation: str
    timestamp: datetime
    result_status: str
    proposal_id: str | None = None
    error_category: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIResponse:
    answer: str
    evidence: tuple[str, ...] = ()
    suggested_actions: tuple[str, ...] = ()
    proposals: tuple[AIActionProposal, ...] = ()
    provider: str = ""
    model: str = ""


def coerce_task_type(value: AITaskType | str) -> AITaskType:
    try:
        return value if isinstance(value, AITaskType) else AITaskType(str(value))
    except ValueError as exc:
        raise ValueError("Unknown AI task type.") from exc
