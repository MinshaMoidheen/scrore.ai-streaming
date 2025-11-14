# models/user.py

from datetime import datetime, timezone
from typing import Optional, ForwardRef

from beanie import Document, Link, Indexed
from pydantic import EmailStr, Field, model_validator

from .core import Role, SoftDelete, UserRef

# --- Type Forward References ---
SectionRef = ForwardRef("Section")
CourseClassRef = ForwardRef("CourseClass")

# --- Beanie Document Models ---


class User(Document):
    """Represents a user, who can be a superadmin, admin, or student."""
    name: str = Field(max_length=50)
    email: Optional[Indexed(EmailStr, unique=True)] = Field(default=None, max_length=50)
    password: str
    role: Role
    phone: Optional[str] = Field(default=None, max_length=15)
    section: Optional[Link[SectionRef]] = None
    courseClass: Optional[Link[CourseClassRef]] = None
    roll_number: Optional[str] = Field(default=None, max_length=20)
    parent_name: Optional[str] = Field(default=None, max_length=50)
    parent_phone: Optional[str] = Field(default=None, max_length=15)
    address: Optional[str] = Field(default=None, max_length=200)
    is_deleted: SoftDelete = Field(default_factory=SoftDelete)
    created_at: datetime = Field(default_factory=datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_role_specific_fields(self):
        if self.role == Role.USER and (
            not self.roll_number or not self.courseClass or not self.section
        ):
            raise ValueError("Roll number, courseClass, and section are required for users")
        if self.role in (Role.ADMIN, Role.TEACHER) and (
            not self.courseClass or not self.section
        ):
            raise ValueError(
                "CourseClass and section are required for admins and teachers"
            )
        return self

    async def soft_delete(self, deleted_by: "User"):
        self.is_deleted = SoftDelete(
            status=True,
            deleted_by=Link(deleted_by, document_class=User),
            deleted_at=datetime.now(timezone.utc),
        )
        await self.save()

    class Settings:
        name = "users"
        indexes = [
            [("roll_number", 1), ("courseClass", 1), ("section", 1)],
            {
                "name": "unique_roll_in_courseclass_section",
                "unique": True,
                "partialFilterExpression": {"role": "user", "is_deleted.status": False},
            },
        ]