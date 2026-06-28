import os
import logging
from pymongo import MongoClient, ASCENDING, DESCENDING

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DatabaseInitializer")

def initialize_database():
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = os.getenv("DB_NAME", "form_builder_db")

    logger.info(f"Connecting to MongoDB at: {MONGO_URI}")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    
    try:
        # Check connection
        client.server_info()
        logger.info("MongoDB connection successful.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        return False

    db = client[DB_NAME]

    # --- 1. PROJECTS COLLECTION INDEXES ---
    logger.info("Initializing 'projects' indexes...")
    projects_col = db["projects"]
    projects_col.create_index([("organization_id", ASCENDING)])
    projects_col.create_index([("created_at", DESCENDING)])

    # --- 2. FORMS COLLECTION INDEXES ---
    logger.info("Initializing 'forms' indexes...")
    forms_col = db["forms"]
    forms_col.create_index([("project_id", ASCENDING)])
    forms_col.create_index([("organization_id", ASCENDING)])
    forms_col.create_index([("theme_id", ASCENDING)])

    # --- 3. THEMES COLLECTION INDEXES ---
    logger.info("Initializing 'themes' indexes...")
    themes_col = db["themes"]
    themes_col.create_index([("organization_id", ASCENDING)])

    # --- 4. RESPONSES COLLECTION INDEXES (For Form Analyser compatibility) ---
    logger.info("Initializing 'responses' indexes...")
    responses_col = db["responses"]
    # Compound index for filtering by form and sorting by time
    responses_col.create_index([("form_id", ASCENDING), ("submitted_at", DESCENDING)])
    # Single field index for organization segmentation
    responses_col.create_index([("organization_id", ASCENDING)])
    # Compound index for analytics tracking
    responses_col.create_index([("form_id", ASCENDING), ("status", ASCENDING)])

    # --- 5. COMMITS COLLECTION INDEXES ---
    logger.info("Initializing 'commits' indexes...")
    commits_col = db["commits"]
    commits_col.create_index([("form_id", ASCENDING), ("hash", ASCENDING)], unique=True)
    commits_col.create_index([("timestamp", DESCENDING)])

    logger.info("All database collections initialized and indexed successfully.")
    return True

if __name__ == "__main__":
    initialize_database()
