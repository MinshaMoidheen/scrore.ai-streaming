from beanie import PydanticObjectId
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from jose import ExpiredSignatureError, JWTError, jwt
from typing import Annotated
from app.config.env_settings import settings
from app.core.auth import ALGORITHM, create_access_token
from app.db_models.token import Token
from pydantic import BaseModel


class AccessTokenResponse(BaseModel):
    accessToken: str


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
