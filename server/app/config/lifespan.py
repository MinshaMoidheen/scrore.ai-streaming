'''Lifespan context manager for the FastAPI application.'''


import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config.db import init_db, db, client

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application.
    Initializes the database connection and Gemini model at startup and closes them at shutdown.
    """
    try:
        # Create videos_recorded directory if it doesn't exist
        videos_dir = "videos_recorded"
        os.makedirs(videos_dir, exist_ok=True)
        print(f"Videos directory ready: {os.path.abspath(videos_dir)}")
        
        await init_db()
        print(f"Connecting database: {db}")
        yield
    except Exception as e:
        print(f"Error during startup: {e}")
        raise
    finally:
        print("Cleaning up...")
        client.close()
        print("Database disconnected")