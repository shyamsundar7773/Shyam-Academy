"""Persistence boundary for Advanced AI tasks, proposals, and audit events."""

import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from models.ai import AIActionProposal, AIAuditEvent, AITask, AITaskStatus, AITaskType, ProposalStatus, coerce_task_type


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(value):
    return datetime.fromisoformat(value) if value else None


def _task(row):
    if not row:
        return None
    return AITask(
        row["task_id"], row["user_id"], AITaskType(row["task_type"]),
        AITaskStatus(row["status"]), row["agent_id"], _dt(row["created_at"]),
        _dt(row["started_at"]), _dt(row["completed_at"]), row["input_summary"],
        row["output_summary"], json.loads(row["context_json"] or "{}"),
        row["provider_reference"], tuple(json.loads(row["action_references_json"] or "[]")),
        row["error_category"], row["error_message"],
    )


def create_task(connection: sqlite3.Connection, user_id: str, task_type, agent_id: str,
                input_summary: str = "", context: dict | None = None) -> AITask:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A user identity is required.")
    task_type = coerce_task_type(task_type)
    task_id = str(uuid4())
    created = _now()
    connection.execute(
        """INSERT INTO ai_tasks
        (task_id,user_id,task_type,agent_id,status,created_at,input_summary,context_json)
        VALUES (?,?,?,?,?,?,?,?)""",
        (task_id, user_id, task_type.value, agent_id, AITaskStatus.CREATED.value,
         created, input_summary[:500], json.dumps(context or {}, separators=(",", ":"))),
    )
    connection.commit()
    return get_task(connection, task_id, user_id)


def get_task(connection, task_id: str, user_id: str) -> AITask | None:
    row = connection.execute(
        "SELECT * FROM ai_tasks WHERE task_id=? AND user_id=?", (task_id, user_id)
    ).fetchone()
    return _task(row)


def list_tasks(connection, user_id: str, limit: int = 50) -> list[AITask]:
    rows = connection.execute(
        "SELECT * FROM ai_tasks WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, max(1, min(int(limit), 200))),
    ).fetchall()
    return [_task(row) for row in rows]


def update_task(connection, task_id: str, user_id: str, **changes) -> AITask:
    allowed = {"status", "started_at", "completed_at", "output_summary",
               "provider_reference", "action_references", "error_category", "error_message"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError("Unknown AI task field.")
    values = dict(changes)
    if "status" in values:
        values["status"] = coerce_status(values["status"]).value
    if "action_references" in values:
        values["action_references"] = json.dumps(list(values["action_references"]))
    assignments = []
    params = []
    for key, value in values.items():
        column = "action_references_json" if key == "action_references" else key
        assignments.append(f"{column}=?")
        params.append(value)
    if assignments:
        params.extend([task_id, user_id])
        cursor = connection.execute(
            f"UPDATE ai_tasks SET {','.join(assignments)} WHERE task_id=? AND user_id=?",
            params,
        )
        if cursor.rowcount != 1:
            raise ValueError("AI task not found.")
        connection.commit()
    return get_task(connection, task_id, user_id)


def coerce_status(value):
    return value if isinstance(value, AITaskStatus) else AITaskStatus(str(value))


def create_proposal(connection, task_id: str, user_id: str, agent_id: str,
                    action_type: str, summary: str, payload: dict,
                    target_reference: str = "", expires_at: str | None = None) -> AIActionProposal:
    if not summary.strip() or not isinstance(payload, dict):
        raise ValueError("Proposal summary and structured payload are required.")
    task = get_task(connection, task_id, user_id)
    if not task:
        raise ValueError("AI task not found.")
    expires = expires_at or datetime.fromisoformat(_now()).replace(
        microsecond=0
    ).isoformat()
    if expires_at is None:
        from datetime import timedelta
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    proposal_id = str(uuid4())
    try:
        connection.execute(
            """INSERT INTO ai_action_proposals
            (proposal_id,task_id,user_id,agent_id,action_type,target_reference,summary,
             structured_payload_json,created_at,expires_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (proposal_id, task_id, user_id, agent_id, action_type, target_reference,
             summary.strip()[:500], json.dumps(payload, separators=(",", ":")),
             _now(), expires),
        )
    except sqlite3.IntegrityError:
        row = connection.execute(
            """SELECT * FROM ai_action_proposals WHERE task_id=? AND user_id=?
            AND action_type=? AND target_reference=?""",
            (task_id, user_id, action_type, target_reference),
        ).fetchone()
        return _proposal(row)
    connection.commit()
    return get_proposal(connection, proposal_id, user_id)


def _proposal(row):
    if not row:
        return None
    return AIActionProposal(
        row["proposal_id"], row["task_id"], row["user_id"], row["agent_id"],
        row["action_type"], row["target_reference"], row["summary"],
        json.loads(row["structured_payload_json"]), _dt(row["created_at"]),
        _dt(row["expires_at"]), ProposalStatus(row["status"]), _dt(row["approved_at"]),
        _dt(row["executed_at"]), row["error_category"], row["error_message"],
    )


def get_proposal(connection, proposal_id: str, user_id: str) -> AIActionProposal | None:
    row = connection.execute(
        "SELECT * FROM ai_action_proposals WHERE proposal_id=? AND user_id=?",
        (proposal_id, user_id),
    ).fetchone()
    return _proposal(row)


def list_proposals(connection, user_id: str, limit: int = 50) -> list[AIActionProposal]:
    rows = connection.execute(
        "SELECT * FROM ai_action_proposals WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, max(1, min(int(limit), 200))),
    ).fetchall()
    return [_proposal(row) for row in rows]


def update_proposal(connection, proposal_id: str, user_id: str, status,
                    error_category=None, error_message=None) -> AIActionProposal:
    status = status if isinstance(status, ProposalStatus) else ProposalStatus(str(status))
    now = _now()
    approved = now if status == ProposalStatus.APPROVED else None
    executed = now if status == ProposalStatus.EXECUTED else None
    cursor = connection.execute(
        """UPDATE ai_action_proposals SET status=?,approved_at=COALESCE(?,approved_at),
        executed_at=COALESCE(?,executed_at),error_category=?,error_message=?
        WHERE proposal_id=? AND user_id=?""",
        (status.value, approved, executed, error_category, error_message, proposal_id, user_id),
    )
    if cursor.rowcount != 1:
        raise ValueError("Proposal not found.")
    connection.commit()
    return get_proposal(connection, proposal_id, user_id)


def add_audit(connection, task_id: str, user_id: str, agent_id: str, operation: str,
               result_status: str, proposal_id: str | None = None,
               error_category: str | None = None, metadata: dict | None = None) -> AIAuditEvent:
    if not get_task(connection, task_id, user_id):
        raise ValueError("AI task not found.")
    audit_id = str(uuid4())
    connection.execute(
        """INSERT INTO ai_audit_log
        (audit_id,task_id,user_id,agent_id,operation,timestamp,result_status,proposal_id,
         error_category,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (audit_id, task_id, user_id, agent_id, operation, _now(), result_status,
         proposal_id, error_category, json.dumps(metadata or {}, separators=(",", ":"))),
    )
    connection.commit()
    row = connection.execute(
        "SELECT * FROM ai_audit_log WHERE audit_id=? AND user_id=?", (audit_id, user_id)
    ).fetchone()
    return AIAuditEvent(
        row["audit_id"], row["task_id"], row["user_id"], row["agent_id"], row["operation"],
        _dt(row["timestamp"]), row["result_status"], row["proposal_id"], row["error_category"],
        json.loads(row["metadata_json"] or "{}"),
    )


def list_audit(connection, user_id: str, limit: int = 100) -> list[AIAuditEvent]:
    rows = connection.execute(
        "SELECT * FROM ai_audit_log WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
        (user_id, max(1, min(int(limit), 200))),
    ).fetchall()
    return [
        AIAuditEvent(r["audit_id"], r["task_id"], r["user_id"], r["agent_id"], r["operation"],
                     _dt(r["timestamp"]), r["result_status"], r["proposal_id"],
                     r["error_category"], json.loads(r["metadata_json"] or "{}"))
        for r in rows
    ]


class AITaskRepository:
    """Object facade for callers that prefer dependency-injected repositories."""

    def __init__(self, connection):
        self.connection = connection

    def create_task(self, *args, **kwargs):
        return create_task(self.connection, *args, **kwargs)

    def get_task(self, *args, **kwargs):
        return get_task(self.connection, *args, **kwargs)

    def list_tasks(self, *args, **kwargs):
        return list_tasks(self.connection, *args, **kwargs)

    def create_proposal(self, *args, **kwargs):
        return create_proposal(self.connection, *args, **kwargs)

    def get_proposal(self, *args, **kwargs):
        return get_proposal(self.connection, *args, **kwargs)

    def list_proposals(self, *args, **kwargs):
        return list_proposals(self.connection, *args, **kwargs)

    def add_audit(self, *args, **kwargs):
        return add_audit(self.connection, *args, **kwargs)

    def list_audit(self, *args, **kwargs):
        return list_audit(self.connection, *args, **kwargs)


TaskRepository = AITaskRepository
