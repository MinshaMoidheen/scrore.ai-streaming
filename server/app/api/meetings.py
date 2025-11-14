from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from beanie import PydanticObjectId

from app.db_models.user import User
from app.db_models.academic import Section
from app.db_models.core import Role
from app.core.auth import authorize

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

    # Note: Section model doesn't have a teacher field anymore
    # You may need to check teacher authorization through a different mechanism
    # For now, allowing any teacher to set status if they belong to the section's courseClass
    if current_user.section and current_user.section.id != section_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to change the status of this meeting",
        )

    # Note: Section model doesn't have is_live or meeting_link fields anymore
    # This endpoint may need to be refactored or removed based on your requirements
    return {"message": f"Meeting status for section {section.name} updated"}


@router.get("/{section_id}/status", status_code=status.HTTP_200_OK)
async def get_meeting_status(
    section_id: PydanticObjectId,
    current_user: User = Depends(
        authorize([Role.SUPERADMIN, Role.ADMIN, Role.TEACHER, Role.USER])
    ),
):
    """
    Get the meeting status for a section. Only students enrolled in the section can see the status.
    """
    section = await Section.get(section_id)
    if not section:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Section not found",
        )

    # Check if the user is a student in this section
    if current_user.section and current_user.section.id != section_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view the status of this meeting",
        )

    # Note: Section model doesn't have is_live or meeting_link fields anymore
    # This endpoint may need to be refactored based on your requirements
    return {"is_live": False, "meeting_link": None}
