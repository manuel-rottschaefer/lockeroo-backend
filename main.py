"""Main backend file"""

# Standard imports
import os
from contextlib import asynccontextmanager

# API services
import uvicorn
from fastapi import FastAPI

# Environments
from dotenv import load_dotenv

# MQTT
from src.services.mqtt_services import fast_mqtt

# Database
import src.services.database_services as database

# Routers
from src.routers.account_router import account_router
from src.routers.session_router import session_router
from src.routers.station_router import stationRouter
from src.routers.auth_router import auth_router
from src.routers.review_router import review_router
from src.routers.admin_router import admin_router


@asynccontextmanager
async def _lifespan(_fastapi_app: FastAPI):
    """Context manager for the application lifespan"""
    load_dotenv(dotenv_path='environments/.env')
    await database.setup()
    await fast_mqtt.mqtt_startup()
    # Wait until server shutdown
    yield
    await fast_mqtt.mqtt_shutdown()


# Create app
app = FastAPI(
    title="Lockeroo",
    summary="Lockeroo Backend",
    version="0.0.8",
    # terms_of_service="https://lockeroo.de/tos",
    # contact={
    #    "name": "Manuel Lukas Rottschäfer",
    #    "url": "https://lockeroo.de/team",
    #    "email": "manuel@lockeroo.de",
    # },
    # license_info={
    #    "name": "Apache 2.0",
    #    "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    # },
    lifespan=_lifespan)

# Include routers
app.include_router(stationRouter, prefix="/stations", tags=["Stations"])
app.include_router(session_router, prefix="/sessions", tags=["Sessions"])
app.include_router(account_router, prefix="/account",
                   tags=["Personal Account"])
app.include_router(auth_router, prefix='/auth', tags=['Authentification'])
app.include_router(review_router, prefix='/review', tags=['Session Reviews'])
app.include_router(admin_router, prefix='/admin',
                   tags=['Administrative endpoints'])

if __name__ == "__main__":
    os.system('clear')
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=80, reload=True, log_config=None)
