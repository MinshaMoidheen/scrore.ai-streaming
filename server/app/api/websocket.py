from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, status
from app.core.meeting_manager import manager
from app.core.auth import ALGORITHM
from app.config.env_settings import settings
from app.db_models.user import User
from app.db_models.student import Student
from app.db_models.core import Role
from beanie import PydanticObjectId
from jose import JWTError, jwt, ExpiredSignatureError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


async def decode_and_validate_token(token: str):
    """
    Decode JWT token and determine if it's a user or student token.
    Returns (entity_id, entity_type) where entity_type is "user" or "student".
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        entity_id: str = payload.get("userId")
        token_type: str = payload.get("type")
        subject: str = payload.get("sub")
        
        if entity_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing userId",
            )
        
        if subject != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token subject: {subject}",
            )
        
        # If token has type="student", it's a student token
        if token_type == "student":
            return (PydanticObjectId(entity_id), "student")
        else:
            # Default to user token (no type field or type="user")
            return (PydanticObjectId(entity_id), "user")
            
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    token: str = Query(..., description="JWT access token for authentication"),
):
    """
    WebSocket endpoint for meeting connections.
    Requires authentication via token query parameter.
    Supports both User (teacher) and Student authentication.
    """
    participant_id = None
    participant_type = None
    
    # Accept the WebSocket connection first (required before any operations)
    await websocket.accept()
    
    try:
        # Decode token to determine if it's a user or student
        entity_id, entity_type = await decode_and_validate_token(token)
        
        if entity_type == "user":
            # Authenticate as User (teacher)
            user = await User.get(entity_id)
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found",
                )
            
            # Check if user is a teacher
            if user.role == Role.TEACHER:
                participant_id = str(user.id)
                participant_type = "teacher"
                logger.info(f"Teacher {participant_id} connecting to room {room_id}")
            else:
                # Non-teacher users are not allowed in meetings
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only teachers and students can join meetings",
                )
        elif entity_type == "student":
            # Authenticate as Student
            student = await Student.get(entity_id)
            
            if not student:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Student not found",
                )
            
            # Check if student is soft-deleted
            if student.is_deleted and student.is_deleted.status:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Student account has been deleted",
                )
            
            participant_id = str(student.id)
            participant_type = "student"
            logger.info(f"Student {participant_id} connecting to room {room_id}")
        
        # Connect to meeting
        await manager.handle_connect(room_id, participant_id, websocket, participant_type)
        
        try:
            while True:
                data = await websocket.receive_text()
                await manager.handle_message(room_id, participant_id, data)
        except WebSocketDisconnect:
            await manager.handle_disconnect(room_id, participant_id)
            logger.info(f"Participant {participant_id} ({participant_type}) disconnected from room {room_id}")
    except HTTPException as e:
        logger.warning(f"WebSocket authentication failed for room {room_id}: {str(e.detail)}")
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(e.detail))
        except:
            pass
    except Exception as e:
        logger.error(f"Error in WebSocket connection for room {room_id}: {str(e)}", exc_info=True)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Internal error")
        except:
            pass
        if participant_id:
            await manager.handle_disconnect(room_id, participant_id)
