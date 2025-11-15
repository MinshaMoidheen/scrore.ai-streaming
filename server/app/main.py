'''Main application file'''

from fastapi import FastAPI, Request, HTTPException
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response
from app.api import websocket, recording, meetings, videos, auth
import logging
import os

from app.config.lifespan import lifespan
from app.config.origins import origins

logger = logging.getLogger(__name__)

# Log CORS configuration on startup
logger.info(f"CORS allowed origins: {origins}")

def custom_generate_unique_id(route: APIRoute):
    '''Unique ID for routes'''
    if route.tags and len(route.tags) > 0:
        return f"{route.tags[0]}-{route.name}"
    return route.name

app = FastAPI(
    lifespan=lifespan,
    generate_unique_id_function=custom_generate_unique_id,
    redirect_slashes=True,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Add exception handler to ensure all errors return JSON
# Must be registered BEFORE including routers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Handle both string and dict detail formats
    if isinstance(exc.detail, dict):
        detail = exc.detail
    else:
        detail = {"code": "HTTPException", "message": str(exc.detail)}
    
    logger.error(f"HTTPException: {exc.status_code} - {detail}")
    
    # Get the origin from the request to add CORS headers
    origin = request.headers.get("origin")
    headers = dict(exc.headers) if exc.headers else {}
    
    # Add CORS headers if origin is in allowed origins
    if origin and origin in origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=headers
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    # Get the origin from the request to add CORS headers
    origin = request.headers.get("origin")
    headers = {}
    
    # Add CORS headers if origin is in allowed origins
    if origin and origin in origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Access-Control-Allow-Methods"] = "*"
        headers["Access-Control-Allow-Headers"] = "*"
    
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "InternalServerError", "message": str(exc)}},
        headers=headers
    )

app.include_router(websocket.router)
app.include_router(recording.router)
app.include_router(meetings.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(auth.router)

# Mount videos_recorded folder as static files
# This allows direct access to videos via /videos_recorded/{filename}
# The path matches the internal path used in the streaming route
# videos_recorded folder is at the same level as the server folder
# Get the absolute path: go up from server/app/main.py to server, then up to root, then videos_recorded
def get_videos_dir():
    """Get the absolute path to the videos_recorded directory.
    Checks project root (same level as server folder) first, then current working directory.
    """
    # Try project root first (same level as server folder)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Goes to server/
    project_root = os.path.dirname(base_dir)  # Goes up to project root
    videos_dir = os.path.join(project_root, "videos_recorded")
    
    if os.path.exists(videos_dir):
        return os.path.abspath(videos_dir)
    
    # Fallback: check current working directory
    videos_dir_cwd = os.path.join(os.getcwd(), "videos_recorded")
    if os.path.exists(videos_dir_cwd):
        return os.path.abspath(videos_dir_cwd)
    
    # If neither exists, return the project root path (will be created if needed)
    return os.path.abspath(videos_dir)

videos_dir = get_videos_dir()
if os.path.exists(videos_dir):
    app.mount("/videos_recorded", StaticFiles(directory=videos_dir), name="videos_recorded")
    logger.info(f"Mounted videos_recorded folder as static files at /videos_recorded from: {videos_dir}")
else:
    logger.warning(f"videos_recorded directory does not exist. Checked: {videos_dir}")



