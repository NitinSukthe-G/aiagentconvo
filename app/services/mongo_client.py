"""One MongoDB connection, shared across services."""

from pymongo import MongoClient

from app.config import settings

mongo_client: MongoClient = MongoClient(settings.mongodb_uri)
db = mongo_client[settings.mongodb_db]

doctors_col = db["doctors"]
slots_col = db["slots"]
appointments_col = db["appointments"]
conversations_col = db["conversations"]
