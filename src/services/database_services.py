"""Provides utility functions for the database."""
# Basics
from uuid import UUID
from bson import Binary
import json
import os
# Database utilities
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import PydanticObjectId as ObjId, init_beanie
# Models
from src.models.action_models import ActionModel
from src.models.billing_models import BillModel
from src.models.locker_models import LockerModel
from src.models.maintenance_models import MaintenanceModel
from src.models.payment_models import PaymentModel
from src.models.review_models import ReviewModel
from src.models.session_models import SessionModel
from src.models.station_models import StationModel
from src.models.task_models import TaskItemModel
from src.models.user_models import UserModel
# Services
from src.services.logging_services import logger_service as logger


async def setup():
    """Initialize the database"""
    if os.getenv('STARTUP_RESET') == 'True':
        await restore_mongodb_data(os.getenv('MONGO_DUMP'))
        logger.new_section()

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
            UserModel,
            BillModel,
            PaymentModel,
            ReviewModel
        ]
    )


def convert_oid(document):
    """Convert $oid fields to ObjectId"""
    for key, value in document.items():
        if isinstance(value, dict) and "$oid" in value:
            document[key] = ObjId(value["$oid"])
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    convert_oid(item)
    return document


async def resolve_station_reference(station_ref):
    """Resolve station reference to ObjectId"""
    if "$callsign" in station_ref:
        station = await db.stations.find_one({"callsign": station_ref["$callsign"]})
        if station:
            return station["_id"]
    return None


async def restore_json_mock_data(directory):
    """Load JSON files into the database"""
    logger.info("Restoring mock data")

    for filename in sorted(os.listdir(directory), reverse=True):
        if not filename.endswith(".json"):
            continue

        collection_name = filename.split(".")[0]
        collection = db[collection_name]
        await collection.drop()  # Drop the collection first

        with open(os.path.join(directory, filename), "r", encoding="utf-8") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                # Map lockers to their stations
                if filename == 'lockers.json':
                    stations = await db.stations.find().to_list(length=None)
                    for locker in data:
                        for station in stations:
                            if locker['station']['$callsign'] == station['callsign']:
                                locker['station']['$id'] = station['_id']
                                del locker["station"]["$callsign"]
                                break

                # Create UUIDs for users
                if filename == 'users.json':
                    for user in data:
                        print(user['fief_id'])
                        user['fief_id'] = Binary.from_uuid(
                            UUID(user['fief_id']))

                await collection.insert_many(data)


async def restore_mongodb_data(directory):
    """Restore MongoDB data with mongorestore."""
    logger.info("Resetting MongoDB database with mongorestore.")
    os.system(
        "mongosh --eval 'use Lockeroo' --eval 'db.dropDatabase()' > /dev/null 2>&1")
    os.system(f"mongorestore --drop {directory} > /dev/null 2>&1")


URI = f"mongodb://{os.getenv('DB_USER')
                   }:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}"
client = AsyncIOMotorClient(URI)

db = client["Lockeroo"]
