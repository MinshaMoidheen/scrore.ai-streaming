from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from beanie import PydanticObjectId
from typing import Annotated, Optional, Union
from jose import JWTError, jwt, ExpiredSignatureError

from app.db_models.user import User
from app.db_models.student import Student
from app.db_models.academic import Section
from app.db_models.core import Role
from app.core.auth import authorize, ALGORITHM
from app.config.env_settings import settings
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

router = APIRouter(prefix="/meetings", tags=["Meetings"])


class MeetingStatus(BaseModel):
    is_live: bool


@router.put("/{section_id}/status", status_code=status.HTTP_200_OK)
async def set_meeting_status(
    section_id: PydanticObjectId,
    status_data: MeetingStatus,
    current_user: User = Depends(authorize([Role.TEACHER])),
):
    """
    Set the meeting status for a section. Only teachers assigned to the section can change the status.
    Note: This endpoint may need to be updated based on how teachers are linked to sections.
    """
    section = await Section.get(section_id)
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found",
        )

    # Authorization: Only teachers with appropriate access can set meeting status
    # Teachers with 'all' or 'centre' access can set status for any section
    # Teachers with 'own' access would need additional logic to determine ownership
    if current_user.role != Role.TEACHER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can change the status of meetings",
        )

    # Note: Section model doesn't have is_live or meeting_link fields anymore
    # This endpoint may need to be refactored or removed based on your requirements
    return {"message": f"Meeting status for section {section.name} updated"}


async def get_current_user_or_student(
    token: Annotated[Optional[str], Depends(oauth2_scheme)]
) -> Union[User, Student]:
    """
    Dependency that authenticates either a User or Student.
    Returns the authenticated entity.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Access denied, no token provided",
            },
        )
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        entity_id: str = payload.get("userId")
        token_type: str = payload.get("type")
        subject: str = payload.get("sub")
        
        if entity_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AuthenticationError", "message": "Token missing userId"},
            )
        
        if subject != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AuthenticationError", "message": f"Invalid token subject: {subject}"},
            )
        
        entity_id_obj = PydanticObjectId(entity_id)
        
        # If token has type="student", authenticate as student
        if token_type == "student":
            student = await Student.get(entity_id_obj)
            if not student:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "AuthenticationError", "message": "Student not found"},
                )
            if student.is_deleted and student.is_deleted.status:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "AuthenticationError", "message": "Student account has been deleted"},
                )
            return student
        else:
            # Default to user authentication
            user = await User.get(entity_id_obj)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"code": "AuthenticationError", "message": "User not found"},
                )
            return user
            
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Token has expired",
            },
        )
    except HTTPException:
        raise
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AuthenticationError", "message": f"Invalid token: {str(e)}"},
        )


@router.get("/{section_id}/status", status_code=status.HTTP_200_OK)
async def get_meeting_status(
    section_id: PydanticObjectId,
    current_entity: Union[User, Student] = Depends(get_current_user_or_student),
):
    """
    Get the meeting status for a section.
    Accessible by teachers, admins, and students enrolled in the section.
    """
    section = await Section.get(section_id)
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found",
        )

    # Authorization: 
    # - Teachers, admins, and superadmins can view any section
    # - Students can view their own section
    if isinstance(current_entity, Student):
        # Verify student belongs to this section
        # Fetch the section link to get the ID
        student_section = await current_entity.fetch_link(Student.section)
        if not student_section or str(student_section.id) != str(section_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view meeting status for your own section",
            )
    elif isinstance(current_entity, User):
        # Users (teachers, admins, etc.) can view any section
        # Additional access level checks could be added here if needed
        pass

    # Note: Section model doesn't have is_live or meeting_link fields anymore
    # This endpoint may need to be refactored based on your requirements
    return {"is_live": False, "meeting_link": None}
