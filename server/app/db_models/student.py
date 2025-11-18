# models/student.py

from datetime import datetime, timezone
from typing import Optional

from beanie import Document, Link
from pydantic import Field, field_validator, model_validator
from pymongo import IndexModel
import bcrypt

from .core import SoftDelete, UserRef, CourseClassRef, SectionRef

# --- Beanie Document Models ---


class Student(Document):
    """Represents a student in the system."""
    username: str = Field(max_length=50)
    password: str
    courseClass: Link[CourseClassRef]
    section: Link[SectionRef]
    rollNumber: str = Field(max_length=20)
    role: str = Field(default="student", pattern="^student$")
    is_deleted: SoftDelete = Field(default_factory=SoftDelete)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("password", mode="before")
    @classmethod
    def hash_password(cls, v) -> str:
        """Hash password before saving if it's a plain string."""
        if v is None:
            return v
        if isinstance(v, str):
            # Only hash if it's not already hashed (bcrypt hashes start with $2b$)
            if not v.startswith("$2b$") and not v.startswith("$2a$"):
                return bcrypt.hashpw(v.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")
        return v

    @model_validator(mode="before")
    @classmethod
    def validate_password_on_create(cls, data) -> dict:
        """Ensure password is provided on creation."""
        if isinstance(data, dict) and "password" in data:
            password = data["password"]
            if not password or (isinstance(password, str) and not password.strip()):
                raise ValueError("Password is required")
        return data

    async def soft_delete(self, deleted_by):
        """Soft delete the student."""
        from .user import User
        self.is_deleted = SoftDelete(
            status=True,
            deleted_by=Link(deleted_by, document_class=User),
            deleted_at=datetime.now(timezone.utc),
        )
        await self.save()

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash."""
        return bcrypt.checkpw(password.encode("utf-8"), self.password.encode("utf-8"))

    class Settings:
        name = "students"
        indexes = []

