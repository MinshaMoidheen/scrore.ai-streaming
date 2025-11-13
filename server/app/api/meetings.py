from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from beanie import PydanticObjectId

from app.db_models.user import User
from app.db_models.academic import Division
from app.db_models.core import Role
from app.core.auth import authorize

router = APIRouter(prefix="/meetings", tags=["Meetings"])


class MeetingStatus(BaseModel):
    is_live: bool


@router.put("/{division_id}/status", status_code=status.HTTP_200_OK)
async def set_meeting_status(
    division_id: PydanticObjectId,
    status_data: MeetingStatus,
    current_user: User = Depends(authorize([Role.TEACHER])),
):
    """
    Set the meeting status for a division. Only the assigned teacher can change the status.
    """
    division = await Division.get(division_id)
    if not division:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Division not found",
        )

    if not division.teacher or division.teacher.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to change the status of this meeting",
        )

    division.is_live = status_data.is_live
    await division.save()

    return {"message": f"Meeting status for division {division.name} updated to {division.is_live}"}


@router.get("/{division_id}/status", status_code=status.HTTP_200_OK)
async def get_meeting_status(
    division_id: PydanticObjectId,
    current_user: User = Depends(
        authorize([Role.SUPERADMIN, Role.ADMIN, Role.TEACHER, Role.USER])
    ),
):
    """
    Get the meeting status for a division. Only students enrolled in the division can see the status.
    """
    division = await Division.get(division_id)
    if not division:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Division not found",
        )

    # Check if the user is a student in this division
    if current_user.division.id != division_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view the status of this meeting",
        )

    return {"is_live": division.is_live, "meeting_link": division.meeting_link}
