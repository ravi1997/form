import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/form_analyser")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "form_analyser")
    FORM_RESPONSES_COLLECTION = os.getenv("FORM_RESPONSES_COLLECTION", "form_responses")
    ANALYSIS_DEFINITIONS_COLLECTION = os.getenv("ANALYSIS_DEFINITIONS_COLLECTION", "analysis_definitions")
    ANALYSIS_RESULTS_COLLECTION = os.getenv("ANALYSIS_RESULTS_COLLECTION", "analysis_results")
    API_KEYS_COLLECTION = os.getenv("API_KEYS_COLLECTION", "api_keys")
    WEBHOOKS_COLLECTION = os.getenv("WEBHOOKS_COLLECTION", "webhooks")
    FORMS_COLLECTION = os.getenv("FORMS_COLLECTION", "forms")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # Set to False in .env to skip auth checks during local development
    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "True").lower() not in ("false", "0", "no")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}

# Default to development
active_config = config_map.get(os.getenv("FLASK_ENV", "development"), DevelopmentConfig)
