"""Provides utility functions for the database."""

# Basics
import json
import os

from beanie import init_beanie
from bson import ObjectId
from dotenv import load_dotenv
# Database utilities
from motor.motor_asyncio import AsyncIOMotorClient

# Services
from src.services.logging_services import logger, new_log_section

# Models
from src.models.action_models import ActionModel
from src.models.locker_models import LockerModel
from src.models.maintenance_models import MaintenanceModel
from src.models.payment_models import PaymentModel
from src.models.session_models import SessionModel
from src.models.station_models import StationModel
from src.models.task_models import TaskItemModel
from src.models.user_models import UserModel


async def setup():
    """Initialize the database"""
    if os.getenv('STARTUP_RESET') == 'True':
        await restore_mongodb_data(os.getenv('MONGO_DUMP'))
        new_log_section()

    await init_beanie(
        database=client["Lockeroo"],
        document_models=[
            StationModel,
            SessionModel,
            ActionModel,
            LockerModel,
            PaymentModel,
            TaskItemModel,
            MaintenanceModel,
            UserModel
        ],
    )


def convert_oid(document):
    """Convert $oid fields to ObjectId"""
    for key, value in document.items():
        if isinstance(value, dict) and "$oid" in value:
            document[key] = ObjectId(value["$oid"])
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    convert_oid(item)
    return document


async def restore_json_mock_data(directory):
    """Load JSON files into the database"""
    logger.info("Restoring mock data")
    for filename in os.listdir(directory):
        if not filename.endswith(".json"):
            continue

        collection_name = filename.split(".")[0]
        collection = db[collection_name]
        await collection.drop()
        with open(os.path.join(directory, filename), "r", encoding="utf-8") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                if collection_name == "stations":
                    db["stations"].create_index([("location", "2dsphere")])
                for item in data:
                    item = convert_oid(item)
                    # if collection_name == "stations":
                    #    station = StationModel(**item)
                    #    await station.insert()
                    # else:
                    await collection.insert_one(item)

            elif data:
                data = convert_oid(data)
                await collection.insert_one(data)


async def restore_mongodb_data(directory):
    """Restore MongoDB data with mongorestore."""
    logger.info("Resetting MongoDB database with mongorestore.")
    os.system(f"mongorestore --drop {directory} > /dev/null 2>&1")


load_dotenv(dotenv_path='environments/.env')
URI = f"mongodb://{os.getenv('DB_USER')
                   }:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}"
client = AsyncIOMotorClient(URI)

db = client["Lockeroo"]
