"""
Lockeroo.database_services
-------------------------
This module provides database interfaces and custom DB utilities

Key Features:
    - Initializes the database connection
    - Links the database to the internal Beanie Documents
    - Handles restore functionality required for docker builds

Dependencies:
    - motor
    - beanie
"""
# Basics
from pathlib import Path
from uuid import UUID
from bson import Binary
import asyncio
import json
import os
# Database utilities
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import PydanticObjectId as ObjId, init_beanie
# Models
from lockeroo_models.snapshot_models import SnapshotModel
from lockeroo_models.locker_models import LockerModel
from lockeroo_models.maintenance_models import MaintenanceSessionModel
from lockeroo_models.payment_models import PaymentModel
from lockeroo_models.review_models import ReviewModel
from lockeroo_models.session_models import SessionModel
from lockeroo_models.station_models import StationModel
from lockeroo_models.task_models import TaskItemModel
from lockeroo_models.user_models import UserModel
# Services
from src.services.config_services import cfg
from src.services.logging_services import logger_service as logger

# TODO: Convert all of this into a class

# Establish a mongodb connection dict with the values collected in the whole script below
mongo_conn = {
    "host": os.getenv("DOCKER_DB_HOST", cfg.get('MONGODB', 'DB_HOST')),
    "port": cfg.get('MONGODB', 'PORT', fallback='27017'),
    "user": cfg.get('MONGODB', 'DB_USER'),
    "password": cfg.get('MONGODB', 'DB_PASS'),
    "auth_db": cfg.get('MONGODB', 'AUTH_DB', fallback='admin')
}


async def setup():
    """Initialize the database"""
    if cfg.get("BACKEND", "STARTUP_RESET") == 'true':
        await restore_mongodb_data(cfg.get('MONGODB', 'MONGO_DUMP'))
        logger.new_section()

    await init_beanie(
        database=client["Lockeroo"],
        document_models=[
            StationModel,
            SessionModel,
            SnapshotModel,
            LockerModel,
            PaymentModel,
            TaskItemModel,
            MaintenanceSessionModel,
            UserModel,
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
                        user['fief_id'] = Binary.from_uuid(
                            UUID(user['fief_id']))

                await collection.insert_many(data)


async def restore_mongodb_data(directory):
    """Restore MongoDB data with mongorestore."""
    logger.info(">>>Resetting database from mongodump")
    path = Path(__file__).resolve().parent.parent.parent/directory

    dropAllCmd = (
        f"mongosh --host {mongo_conn['host']} --port {mongo_conn['port']} "
        f"--username {mongo_conn['user']} --password {mongo_conn['password']} "
        f"--authenticationDatabase {mongo_conn['auth_db']} "
        f"--eval 'use Lockeroo' "
        f"--eval 'db.dropDatabase()' "
    )
    restoreAllCmd = (
        f"mongorestore "
        f"--host {mongo_conn['host']} "
        f"--port {mongo_conn['port']} "
        f"--username {mongo_conn['user']} "
        f"--password '{mongo_conn['password']}' "
        f"--authenticationDatabase {mongo_conn['auth_db']} "
        f"--drop {path} "
        f"> /dev/null")
    os.system(dropAllCmd)
    os.system(restoreAllCmd)

    await db['stations'].create_index([("location", "2dsphere")])

URI = (
    f"mongodb://{mongo_conn['user']}:{mongo_conn['password']}@"f"{mongo_conn['host']}")
client = AsyncIOMotorClient(URI)

db = client["Lockeroo"]
