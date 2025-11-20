# models/meeting.py

from datetime import datetime, timezone, date
from typing import ForwardRef, Optional, List
import re

from beanie import Document, Link
from pydantic import Field, field_validator

from .core import SoftDelete
from .user import User

# --- Type Forward References ---
UserRef = ForwardRef("User")
CourseClassRef = ForwardRef("CourseClass")
SectionRef = ForwardRef("Section")
SubjectRef = ForwardRef("Subject")


# --- Beanie Document Models ---

class Meeting(Document):
    """Represents a meeting in the system."""
    title: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    date: date
    startTime: str = Field(max_length=5)  # HH:MM format
    endTime: str = Field(max_length=5)  # HH:MM format
    courseClass: Optional[Link[CourseClassRef]] = None
    section: Optional[Link[SectionRef]] = None
    subject: Optional[Link[SubjectRef]] = None
    organizer: Link[UserRef]
    participants: Optional[List[Link[UserRef]]] = Field(default_factory=list)
    is_deleted: SoftDelete = Field(default_factory=SoftDelete)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator('startTime', 'endTime')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate that time is in HH:MM format."""
        pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
        if not re.match(pattern, v):
            raise ValueError('Time must be in HH:MM format')
        return v

    async def soft_delete(self, deleted_by: "User"):
        """Soft delete the meeting."""
        self.is_deleted = SoftDelete(
            status=True,
            deleted_by=Link(deleted_by, document_class=User),
            deleted_at=datetime.now(timezone.utc),
        )
        await self.save()

    class Settings:
        name = "meetings"

