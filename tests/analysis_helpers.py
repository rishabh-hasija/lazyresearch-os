"""Deterministic source analysis fixtures; these do not evaluate model quality."""

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from lazyresearch.application.analysis import segments
from lazyresearch.application.analysis_models import (
    AIError,
    AIResult,
    AnalysisConfig,
    AnalysisOutputSchema,
    AnalysisRequest,
    AnalysisWork,
    CallAttempt,
)
from lazyresearch.application.intake_models import (
    ContentExtraction,
    ExtractionData,
    ExtractionStatus,
    ProcessingLease,
)
from lazyresearch.domain.identity import ContentId, OwnerId


def work_for(text="Submit by 2026-11-07.", config=None, pages=()):
    config = config or AnalysisConfig()
    owner, content, extraction_id = OwnerId(uuid4()), ContentId(uuid4()), uuid4()
    extraction = ContentExtraction(
        id=extraction_id,
        owner_id=owner,
        content_id=content,
        data=ExtractionData(
            status=ExtractionStatus.SUCCEEDED,
            version="fixture-v1",
            text=text,
            normalized_hash=sha256(text.encode()).hexdigest(),
            pages=pages,
        ),
    )
    work = AnalysisWork(
        lease=ProcessingLease(
            id=uuid4(),
            owner_id=owner,
            content_id=content,
            extraction_id=extraction_id,
            kind="ANALYZE",
            version="fixture-analysis-v1",
            token=uuid4(),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        ),
        run_id=uuid4(),
        extraction=extraction,
        processing=config.identity(sha256(text.encode()).hexdigest()),
    )
    request = AnalysisRequest(
        owner, content, extraction_id, segments(extraction, config)[0], config
    )
    return work, request


def payload(request, *, action=True, deadline="2026-11-07"):
    evidence = {
        "content_id": str(request.content_id),
        "extraction_id": str(request.extraction_id),
        "start": request.segment.start,
        "end": request.segment.end,
        "quote": request.segment.text,
        "page": request.segment.page,
    }
    return {
        "schema_version": request.config.schema_version,
        "summary": "Source overview.",
        "topics": ["Applications"],
        "entities": [],
        "claims": [
            {
                "text": "The source requests submission.",
                "uncertainty": "medium",
                "evidence": [evidence],
            }
        ],
        "actionability": "action_required" if action else "no_action",
        "actions": [
            {
                "title": "Submit application",
                "description": "Review and submit.",
                "kind": "application",
                "deadline_raw": deadline,
                "uncertainty": "low",
                "evidence": [evidence],
            }
        ]
        if action
        else [],
    }


def parsed(value):
    return AnalysisOutputSchema.model_validate_json(json.dumps(value))


class FakeProcessor:
    def __init__(self, *, error=None, deadline="2026-11-07", action=True, callback=None):
        self.error, self.deadline, self.action, self.callback = error, deadline, action, callback
        self.requests = []

    def analyze(self, request):
        self.requests.append(request)
        if self.callback:
            self.callback(request)
        now = datetime.now(UTC)
        attempts = (CallAttempt(now, now, 0, self.error or "OK", False),)
        if self.error:
            raise AIError(self.error, attempts)
        return AIResult(
            parsed(payload(request, action=self.action, deadline=self.deadline)), attempts
        )


class FakeWire:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def __call__(self, path, body, timeout):
        self.calls.append((path, body, timeout))
        if self.responses:
            value = self.responses.pop(0)
            if isinstance(value, Exception):
                raise value
            if isinstance(value, dict):
                return value
            content = value
        else:
            envelope = json.loads(body["messages"][1]["content"])
            content = json.dumps(
                {
                    "schema_version": "analysis-v2",
                    "summary": "Source overview.",
                    "topics": [],
                    "entities": [],
                    "claims": [
                        {
                            "text": "Source states a request.",
                            "uncertainty": "medium",
                            "evidence": [envelope["evidence_id"]],
                        }
                    ],
                    "actionability": "no_action",
                    "actions": [],
                }
            )
        return {
            "model": body["model"],
            "done": True,
            "done_reason": "stop",
            "message": {"content": content},
        }
