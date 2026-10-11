"""Commitment acceptance, rejection, timing, and completion reports."""

from __future__ import annotations

import uuid
from datetime import datetime

from outmark.clock import Clock
from outmark.errors import TransitionError, ValidationError
from outmark.history import HistoryGrid, build_grid
from outmark.records import (
    ActivityDraft,
    CompletionReport,
    Proposal,
    ProposalStatus,
    Session,
    SessionSnapshot,
    SessionStatus,
)
from outmark.storage import Document, JsonStore
from outmark.validation import (
    INSTRUCTIONS_LIMIT,
    QUESTION_LIMIT,
    REFLECTION_LIMIT,
    TITLE_LIMIT,
    optional_text,
    require_category,
    require_duration,
    require_outcome,
    require_text,
)

_PROGRESS_SEGMENTS = 13


class SessionEngine:
    """The authoritative session lifecycle. Display and inference stay outside."""

    def __init__(self, store: JsonStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock
        self._document = store.load()
        self._anchors: dict[str, float] = {}
        self._recover_anchors()

    def propose(self, draft: ActivityDraft) -> Proposal:
        """Record one open suggestion. This does not start a timer."""
        self._require_idle("request another activity")
        proposal = Proposal(
            id=_new_id(),
            created_at=self._wall(),
            duration_minutes=require_duration(draft.duration_minutes),
            category=require_category(draft.category),
            title=require_text(draft.title, "title", TITLE_LIMIT),
            instructions=require_text(draft.instructions, "instructions", INSTRUCTIONS_LIMIT),
            reflection_question=require_text(
                draft.reflection_question, "reflection_question", QUESTION_LIMIT
            ),
            status=ProposalStatus.PROPOSED,
        )
        self._commit(
            Document(
                default_duration=self._document.default_duration,
                proposals=(*self._document.proposals, proposal),
                sessions=self._document.sessions,
            )
        )
        return proposal

    def reject(self, proposal_id: str) -> Proposal:
        """Reject a suggestion. No session is created."""
        proposal = self._proposal(proposal_id)
        if proposal.status is not ProposalStatus.PROPOSED:
            raise TransitionError("only an open proposal can be rejected")
        updated = _replace_status(proposal, ProposalStatus.REJECTED)
        self._commit(self._with_proposal(updated))
        return updated

    def accept(self, proposal_id: str) -> Session:
        """Accept a suggestion and start its timer."""
        if self._active() is not None:
            raise TransitionError("report the active session before accepting another")
        proposal = self._proposal(proposal_id)
        if proposal.status is not ProposalStatus.PROPOSED:
            raise TransitionError("only an open proposal can be accepted")
        started = self._wall()
        session = Session(
            id=_new_id(),
            proposal_id=proposal.id,
            started_at=started,
            duration_minutes=proposal.duration_minutes,
            category=proposal.category,
            title=proposal.title,
            quest=proposal.instructions,
            reflection_question=proposal.reflection_question,
            status=SessionStatus.ACTIVE,
            reflection=None,
            reported_at=None,
        )
        self._commit(
            Document(
                default_duration=self._document.default_duration,
                proposals=tuple(
                    _replace_status(item, ProposalStatus.ACCEPTED)
                    if item.id == proposal.id
                    else item
                    for item in self._document.proposals
                ),
                sessions=(*self._document.sessions, session),
            )
        )
        self._anchors[session.id] = self._clock.monotonic()
        return session

    def report(self, session_id: str, report: CompletionReport) -> Session:
        """Record an explicit kept or not-kept result."""
        session = self._session(session_id)
        if session.status is not SessionStatus.ACTIVE:
            raise TransitionError("only an active session can be reported")
        duration = session.duration_minutes * 60
        raw_elapsed = self._clock.monotonic() - self._anchors[session.id]
        if raw_elapsed < duration:
            remaining = duration - max(0.0, raw_elapsed)
            raise TransitionError(
                "the commitment can be reported after the timer ends",
                remaining_seconds=remaining,
            )
        outcome = require_outcome(report.outcome)
        reflection = optional_text(report.reflection, "reflection", REFLECTION_LIMIT)
        reported = Session(
            id=session.id,
            proposal_id=session.proposal_id,
            started_at=session.started_at,
            duration_minutes=session.duration_minutes,
            category=session.category,
            title=session.title,
            quest=session.quest,
            reflection_question=session.reflection_question,
            status=SessionStatus(outcome),
            reflection=reflection,
            reported_at=self._wall(),
        )
        self._commit(self._with_session(reported))
        self._anchors.pop(session.id, None)
        return reported

    def open_proposal(self) -> Proposal | None:
        for proposal in self._document.proposals:
            if proposal.status is ProposalStatus.PROPOSED:
                return proposal
        return None

    def active_session(self) -> SessionSnapshot | None:
        """Return the live session. Reading this does not write `kept`."""
        session = self._active()
        if session is None:
            return None
        duration = session.duration_minutes * 60
        raw_elapsed = self._clock.monotonic() - self._anchors[session.id]
        elapsed = min(duration, max(0.0, raw_elapsed))
        ratio = 0.0 if duration == 0 else elapsed / duration
        return SessionSnapshot(
            session=session,
            elapsed_seconds=elapsed,
            deadline_passed=raw_elapsed >= duration,
            progress_segments=min(_PROGRESS_SEGMENTS, int(ratio * _PROGRESS_SEGMENTS)),
        )

    def sessions(self) -> tuple[Session, ...]:
        return self._document.sessions

    def proposals(self) -> tuple[Proposal, ...]:
        return self._document.proposals

    def history(self, today: datetime | None = None) -> HistoryGrid:
        current = self._wall() if today is None else today
        if current.tzinfo is None:
            raise ValidationError("today must be timezone-aware")
        return build_grid(self._document.sessions, current.date())

    def _active(self) -> Session | None:
        for session in self._document.sessions:
            if session.status is SessionStatus.ACTIVE:
                return session
        return None

    def _require_idle(self, action: str) -> None:
        if self.open_proposal() is not None:
            raise TransitionError(f"reject the open proposal before you {action}")
        if self._active() is not None:
            raise TransitionError(f"report the active session before you {action}")

    def _proposal(self, proposal_id: str) -> Proposal:
        for proposal in self._document.proposals:
            if proposal.id == proposal_id:
                return proposal
        raise TransitionError("proposal was not found")

    def _session(self, session_id: str) -> Session:
        for session in self._document.sessions:
            if session.id == session_id:
                return session
        raise TransitionError("session was not found")

    def _with_proposal(self, proposal: Proposal) -> Document:
        return Document(
            default_duration=self._document.default_duration,
            proposals=tuple(
                proposal if item.id == proposal.id else item for item in self._document.proposals
            ),
            sessions=self._document.sessions,
        )

    def _with_session(self, session: Session) -> Document:
        return Document(
            default_duration=self._document.default_duration,
            proposals=self._document.proposals,
            sessions=tuple(
                session if item.id == session.id else item for item in self._document.sessions
            ),
        )

    def _commit(self, document: Document) -> None:
        self._store.save(document)
        self._document = document

    def _wall(self) -> datetime:
        current = self._clock.wall()
        if current.tzinfo is None:
            raise ValidationError("clock must return a timezone-aware time")
        return current.replace(microsecond=0)

    def _recover_anchors(self) -> None:
        now = self._clock.monotonic()
        wall = self._wall()
        for session in self._document.sessions:
            if session.status is not SessionStatus.ACTIVE:
                continue
            elapsed = max(0.0, (wall - session.started_at).total_seconds())
            self._anchors[session.id] = now - elapsed


def _replace_status(proposal: Proposal, status: ProposalStatus) -> Proposal:
    return Proposal(
        id=proposal.id,
        created_at=proposal.created_at,
        duration_minutes=proposal.duration_minutes,
        category=proposal.category,
        title=proposal.title,
        instructions=proposal.instructions,
        reflection_question=proposal.reflection_question,
        status=status,
    )


def _new_id() -> str:
    return uuid.uuid4().hex
