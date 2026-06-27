import os


class Config:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "form-response-service")
    ANALYSER_SYNC_MODE = os.getenv("ANALYSER_SYNC_MODE", "local")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///form_response.db")
