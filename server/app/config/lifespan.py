'''Lifespan context manager for the FastAPI application.'''


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