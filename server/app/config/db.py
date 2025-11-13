'''MongoDB Initialization and connection setup'''

from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from app.config.env_settings import settings

if not settings.MONGO_URI:
    raise ValueError("MONGO_URI is empty or not set")
if not settings.MONGO_URI.startswith(("mongodb://", "mongodb+srv://")):
    raise ValueError("Invalid MONGO_URI scheme")
try:
    client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGO_URI)
    db = client.get_database(settings.database)
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    raise


async def init_db():
    """
    Initialize the Beanie ODM with the MongoDB client and register the models.
    """
    await init_beanie(
        database=db,
        document_models=[
        ]
    )
