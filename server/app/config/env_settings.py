'''Reading data from env file'''

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Settings for the application.
    """
    MONGO_URI: str
    ENV: str = "development"
    database:str = "score-ai"
    JWT_SECRET: str
    JWT_REFRESH_SECRET: str

    class Config:
        '''Env format configs'''
        env_file = ".env"
        env_file_encoding = "utf-8"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


@lru_cache
def get_settings():
    """
    Get the settings for the application.
    """
    return Settings()


settings:Settings = get_settings()