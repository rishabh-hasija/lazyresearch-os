"""Opaque static ID distinctions without runtime wrapper objects or ID generation."""

from typing import NewType
from uuid import UUID

OwnerId = NewType("OwnerId", UUID)
ContentId = NewType("ContentId", UUID)
CaptureId = NewType("CaptureId", UUID)
ExtractionId = NewType("ExtractionId", UUID)
TopicId = NewType("TopicId", UUID)
MissionId = NewType("MissionId", UUID)
ResultId = NewType("ResultId", UUID)
AnalysisId = NewType("AnalysisId", UUID)
ProposalId = NewType("ProposalId", UUID)
ActionId = NewType("ActionId", UUID)
