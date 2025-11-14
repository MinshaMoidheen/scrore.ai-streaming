'''CORS origins configuration for the application.'''

from app.config.env_settings import settings

originsURLs = [
    "http://localhost:3031",
    "http://localhost:8000",
    "http://localhost:3000",
]

origins = originsURLs if settings.ENV != "production" else []
