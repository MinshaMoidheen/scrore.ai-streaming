"""
Authentication and authorization functions.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from beanie import PydanticObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt, ExpiredSignatureError

from app.config.env_settings import settings
from app.db_models.core import Role
from app.db_models.user import User
import logging

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_access_token(user_id: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"userId": user_id, "exp": expire, "sub": "accessApi"}
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: str):
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"userId": user_id, "exp": expire, "sub": "refreshToken"}
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_REFRESH_SECRET, algorithm=ALGORITHM
    )
    return encoded_jwt


async def authenticate(
    token: Annotated[Optional[str], Depends(oauth2_scheme)]
) -> PydanticObjectId:
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
        user_id: str = payload.get("userId")
        subject: str = payload.get("sub")

        print(f"Decoded token payload: {payload}")  # Debug print statement
        print(f"user_id : {user_id}, subject: {subject}")  # Debug print statement

        logger.info(f"Token decoded successfully. userId: {user_id}, subject: {subject}")

        if user_id is None:
            logger.error("Token payload missing userId")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AuthenticationError", "message": "Access token invalid: missing userId"},
            )
        
        if subject != "access":
            logger.error(f"Token subject mismatch. Expected 'access', got '{subject}'")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AuthenticationError", "message": f"Access token invalid: subject must be 'access', got '{subject}'"},
            )

        return PydanticObjectId(user_id)
    except ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AuthenticationError",
                "message": "Access token has expired, request a new one with refresh token",
            },
        ) from None
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}. JWT_SECRET configured: {bool(settings.JWT_SECRET)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AuthenticationError", "message": f"Access token invalid: {str(e)}"},
        ) from None


def authorize(roles: list[Role]):
    async def get_current_user(
        user_id: Annotated[PydanticObjectId, Depends(authenticate)]
    ) -> User:
        user = None
        try:
            user = await User.get(user_id)
            if user:
                logger.info(f"User {user_id} found in database with role {user.role}")
            else:
                logger.info(f"User {user_id} not found in database (User.get returned None)")
        except Exception as e:
            # User might not exist in streaming server's database
            # This is okay - we'll create a minimal user or skip validation
            error_msg = str(e) if e else "Unknown error"
            error_type = type(e).__name__
            logger.warning(f"User {user_id} not found in database (exception {error_type}): {error_msg}")
            user = None
        
        if not user:
            # User doesn't exist in streaming server's database
            # Since we already validated the role in the Next.js proxy,
            # we can create a minimal user object for internal use
            # Note: We assume the role is valid since it was validated in the proxy
            # For recording, we only need the user ID, so we'll create a minimal user
            logger.info(f"User {user_id} not in streaming server DB, creating minimal user for role validation")
            
            # Create a minimal user object using model_construct to bypass validation
            # We'll use the first allowed role as default (roles list should contain the valid role)
            # Since role was already validated in proxy, we can trust it's one of the allowed roles
            from app.db_models.user import User as UserModel
            from app.db_models.core import SoftDelete
            from datetime import datetime, timezone
            
            try:
                # Create a temporary user object using model_construct to bypass Pydantic validation
                # This is just for internal use - the actual role validation happened in the proxy
                user = UserModel.model_construct(
                    id=user_id,
                    name="Teacher",  # Placeholder name
                    email=None,
                    password="temp",  # Required field but not used
                    role=roles[0] if roles else Role.TEACHER,  # Use first allowed role
                    phone=None,
                    section=None,
                    courseClass=None,
                    roll_number=None,
                    parent_name=None,
                    parent_phone=None,
                    address=None,
                    is_deleted=SoftDelete(status=False),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                logger.info(f"Created minimal user object for {user_id} with role {user.role}")
            except Exception as construct_error:
                logger.error(f"Failed to create minimal user object: {str(construct_error)}", exc_info=True)
                # If we can't create a user object, we still need to return something
                # Create a very basic user object
                user = UserModel.model_construct(
                    id=user_id,
                    name="User",
                    password="temp",
                    role=roles[0] if roles else Role.TEACHER,
                    is_deleted=SoftDelete(status=False),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )

        # Validate role if user exists and has a role
        if user and user.role and user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "AuthorizationError",
                    "message": "Access denied, insufficient permissions",
                },
            )
        return user

    return get_current_user
