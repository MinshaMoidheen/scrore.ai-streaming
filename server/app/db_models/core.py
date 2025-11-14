# models/core.py

from datetime import datetime
from enum import Enum
from typing import Optional, ForwardRef

from beanie import Link
from pydantic import BaseModel

# --- Type Forward References for relationships ---
# Define forward references for models that will be imported later.
UserRef = ForwardRef("User")
CourseClassRef = ForwardRef("CourseClass")
SectionRef = ForwardRef("Section")

# --- Reusable Nested Pydantic Models & Enums ---

class SoftDelete(BaseModel):
    """A reusable model for handling soft delete metadata."""
    status: bool = False
    deleted_by: Optional[Link[UserRef]] = None
    deleted_at: Optional[datetime] = None

class Role(str, Enum):
    """Enumeration for user roles."""
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    TEACHER = "teacher"
    USER = "user"

class Access(str, Enum):
    """Enumeration for user access levels."""
    CENTRE = "centre"
    OWN = "own"
    ALL = "all"

class AttendanceStatus(str, Enum):
    """Enumeration for attendance status."""
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"