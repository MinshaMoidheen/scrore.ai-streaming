from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Cookie, HTTPException, Response, status
from jose import ExpiredSignatureError, JWTError, jwt
from typing import Annotated
from app.config.env_settings import settings
from app.core.auth import (
    ALGORITHM,
    create_access_token,
    create_student_access_token,
    create_student_refresh_token,
)
from app.db_models.token import Token
from app.db_models.student import Student
from pydantic import BaseModel


class AccessTokenResponse(BaseModel):
    accessToken: str


class StudentLoginRequest(BaseModel):
    username: str
    password: str


class StudentLoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    studentId: str


router = APIRouter(tags=["Auth"], prefix="/api/auth")


@router.post("/token/refresh", response_model=AccessTokenResponse)
async def refresh_token(
    response: Response,
    refreshToken: Annotated[str | None, Cookie()] = None,
):
    if not refreshToken:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Invalid refresh token",
            },
        )
    try:
        token_exists = await Token.find_one(Token.token == refreshToken)
        if not token_exists:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AuthenticationError",
                    "message": "Invalid refresh token",
                },
            )

        payload = jwt.decode(
            refreshToken, settings.JWT_REFRESH_SECRET, algorithms=[ALGORITHM]
        )
        user_id: str = payload.get("userId")
        subject: str = payload.get("sub")

        if user_id is None or subject != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AuthenticationError",
                    "message": "Invalid refresh token",
                },
            )
        access_token = create_access_token(user_id)
        return {"accessToken": access_token}

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Refresh token has expired, please login again",
            },
        ) from None
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Invalid refresh token",
            },
        ) from None


@router.post("/student/login", response_model=StudentLoginResponse)
async def student_login(credentials: StudentLoginRequest):
    """Authenticate a student and return access and refresh tokens."""
    try:
        # Find student by username
        student = await Student.find_one(Student.username == credentials.username)
        
        if not student:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AuthenticationError",
                    "message": "Invalid username or password",
                },
            )
        
        # Check if student is soft-deleted
        if student.is_deleted and student.is_deleted.status:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AuthenticationError",
                    "message": "Student account has been deleted",
                },
            )
        
        # Verify password
        if not student.verify_password(credentials.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AuthenticationError",
                    "message": "Invalid username or password",
                },
            )
        
        # Create tokens
        access_token = create_student_access_token(str(student.id))
        refresh_token = create_student_refresh_token(str(student.id))
        
        # Save refresh token to database
        token_doc = Token(
            token=refresh_token,
            user_id=student.id,  # Token model uses user_id field, but we'll store student ID here
        )
        await token_doc.insert()
        
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "studentId": str(student.id),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "InternalServerError",
                "message": f"An error occurred during login: {str(e)}",
            },
        ) from None


@router.post("/student/token/refresh", response_model=AccessTokenResponse)
async def refresh_student_token(
    response: Response,
    refreshToken: Annotated[str | None, Cookie()] = None,
):
    """Refresh a student's access token using their refresh token."""
    if not refreshToken:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Invalid refresh token",
            },
        )
    try:
        token_exists = await Token.find_one(Token.token == refreshToken)
        if not token_exists:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AuthenticationError",
                    "message": "Invalid refresh token",
                },
            )

        payload = jwt.decode(
            refreshToken, settings.JWT_REFRESH_SECRET, algorithms=[ALGORITHM]
        )
        student_id: str = payload.get("userId")
        token_type: str = payload.get("type")
        subject: str = payload.get("sub")

        if student_id is None or subject != "refresh" or token_type != "student":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "AuthenticationError",
                    "message": "Invalid refresh token",
                },
            )
        access_token = create_student_access_token(student_id)
        return {"accessToken": access_token}

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Refresh token has expired, please login again",
            },
        ) from None
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Invalid refresh token",
            },
        ) from None
