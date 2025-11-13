'''CORS origins configuration for the application.'''

from app.config.env_settings import settings

originsURLs = [
    "*"
]

origins = originsURLs if settings.ENV != "production" else []
