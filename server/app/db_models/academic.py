# models/academic.py

from datetime import datetime, timezone
from typing import ForwardRef
from typing import Optional

from beanie import Document, Link, Indexed
from pydantic import Field

from .core import SoftDelete
from .user import User

# --- Type Forward References ---
CourseClassRef = ForwardRef("CourseClass")
TeacherRef = ForwardRef("User")

# --- Beanie Document Models ---

class CourseClass(Document):
    """Represents a class or grade."""
    name: Indexed(str, unique=True) = Field(max_length=50)
    description: Optional[str] = Field(default=None, max_length=200)
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
        name = "courseclasses"


class Subject(Document):
    """Represents a subject."""
    name: Indexed(str, unique=True) = Field(max_length=100)
    code: Optional[str] = Field(default=None, max_length=20)
    description: Optional[str] = Field(default=None, max_length=200)
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
        name = "subjects"


class Section(Document):
    """Represents a section within a course class (e.g., Class 10-A)."""
    name: str = Field(max_length=20)
    courseClass: Link[CourseClassRef]
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
        name = "sections"
        indexes = [
            [("name", 1), ("courseClass", 1)],
            {
                "name": "unique_name_in_courseclass",
                "unique": True,
                "partialFilterExpression": {"is_deleted.status": False},
            },
        ]