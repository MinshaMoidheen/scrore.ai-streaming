# models/academic.py

from datetime import datetime, timezone
from typing import ForwardRef
from typing import Optional

from beanie import Document, Link, Indexed
from pydantic import Field

from .core import SoftDelete
from .user import User

# --- Type Forward References ---
ClassRef = ForwardRef("Class")
TeacherRef = ForwardRef("User")

# --- Beanie Document Models ---

class Class(Document):
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
        name = "classes"


# --- Division Model changes---
# meeting_link: Optional[str]: To store the meeting URL for the class.
# is_live: bool: A boolean to indicate if the class is currently live.


class Division(Document):
    """Represents a division within a class (e.g., Class 10-A)."""
    name: str = Field(max_length=20)
    class_id: Link[ClassRef] = Field(alias="class")
    teacher: Optional[Link[TeacherRef]] = Field(default=None)
    description: Optional[str] = Field(default=None, max_length=200)
    meeting_link: Optional[str] = Field(default=None, max_length=255)
    is_live: bool = Field(default=False)
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
        name = "divisions"
        indexes = [
            [("name", 1), ("class_id", 1)],
            {
                "name": "unique_name_in_class",
                "unique": True,
                "partialFilterExpression": {"is_deleted.status": False},
            },
        ]