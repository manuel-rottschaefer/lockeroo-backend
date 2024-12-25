"""Main backend file"""
# Standard imports
from contextlib import asynccontextmanager
# API services
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# Environments
from dotenv import load_dotenv
# Services
from src.services.mqtt_services import fast_mqtt
# Entities
from src.entities.task_entity import start_expiration_manager
# Database
import src.services.database_services as database

# Routers
# from src.routers.user_router import user_router
from src.routers.session_router import session_router
from src.routers.station_router import station_router
from src.routers.auth_router import auth_router
from src.routers.review_router import review_router
from src.routers.admin_router import admin_router
from src.routers.dashboard_router import dashboard_router


@asynccontextmanager
async def _lifespan(_fastapi_app: FastAPI):
    """Context manager for the application lifespan"""
    load_dotenv('environments/.env')
    await database.setup()
    await fast_mqtt.mqtt_startup()
    await start_expiration_manager()
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# Include routers
app.include_router(station_router, prefix="/stations", tags=["Stations"])
app.include_router(session_router, prefix="/sessions", tags=["Sessions"])
# app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(auth_router, prefix='/auth', tags=['Authentification'])
app.include_router(review_router, prefix='/review', tags=['Reviews'])
app.include_router(admin_router, prefix='/admin', tags=['Admin'])
app.include_router(dashboard_router, prefix='/dashboard', tags=['Dashboard'])


if __name__ == "__main__":
    # os.system('clear')
    # Run the server
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
