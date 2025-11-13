# models/attendance.py

from datetime import datetime, timezone
from typing import List, Optional, ForwardRef

from beanie import Document, Link
from pydantic import Field

from .core import SoftDelete, AttendanceStatus

# --- Type Forward References ---
UserRef = ForwardRef("User")
ClassRef = ForwardRef("Class")
DivisionRef = ForwardRef("Division")
AttendanceRef = ForwardRef("Attendance")
User = ForwardRef("User")

# --- Beanie Document Models ---

class Schedule(Document):
    """Represents a scheduled class or event."""
    class_id: Link[ClassRef] = Field(alias="class")
    division: Link[DivisionRef]
    start_time: str
    end_time: str
    topic: str = Field(max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    teacher_id: Optional[Link[UserRef]] = None
    teacher_name: Optional[str] = Field(default=None, max_length=50)
    stream_ended: bool = False
    is_deleted: SoftDelete = Field(default_factory=SoftDelete)
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))

    async def soft_delete(self, deleted_by: "User"):
        self.is_deleted = SoftDelete(
            status=True,
            deleted_by=Link(deleted_by, document_class=User),
            deleted_at=datetime.now(timezone.utc),
        )
        await self.save()

    class Settings:
        name = "schedules"


class Attendance(Document):
    """Represents a single attendance entry for a student on a specific date."""
    student_id: Link[UserRef]
    student_name: str = Field(max_length=50)
    class_id: Link[ClassRef] = Field(alias="class")
    division: Link[DivisionRef]
    date: datetime
    status: AttendanceStatus
    remarks: Optional[str] = Field(default=None, max_length=200)
    marked_by: Optional[Link[UserRef]] = None
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))

    class Settings:
        name = "attendances"
        indexes = [
            [("student_id", 1), ("date", 1)],
            {"name": "unique_attendance_per_student_date", "unique": True},
        ]


class AttendanceRecord(Document):
    """A summary record of attendance for a specific class/division on a given date."""
    date: datetime
    class_id: Link[ClassRef] = Field(alias="class")
    division: Link[DivisionRef]
    students: List[Link[AttendanceRef]]
    total_students: int = Field(ge=0)
    present_count: int = Field(ge=0)
    absent_count: int = Field(ge=0)
    late_count: int = Field(ge=0)
    is_deleted: SoftDelete = Field(default_factory=SoftDelete)
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))

    async def soft_delete(self, deleted_by: "User"):
        self.is_deleted = SoftDelete(
            status=True,
            deleted_by=Link(deleted_by, document_class=User),
            deleted_at=datetime.now(timezone.utc),
        )
        await self.save()

    class Settings:
        name = "attendance_records"
        indexes = [
            [("class_id", 1), ("division", 1), ("date", 1)],
            {
                "name": "unique_record_per_class_div_date",
                "unique": True,
                "partialFilterExpression": {"is_deleted.status": False},
            },
        ]