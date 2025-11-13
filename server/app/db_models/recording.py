from datetime import datetime, timezone
from beanie import Document, Link
from pydantic import Field

from .core import DivisionRef


class RecordedVideo(Document):
    """Represents a recorded video of a class session."""

    filename: str = Field(max_length=255)
    division: Link[DivisionRef]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "recorded_videos"
