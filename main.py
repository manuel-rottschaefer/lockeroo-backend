"""Main backend file"""
# Standard imports
from contextlib import asynccontextmanager
# API services
import uvicorn
from fastapi import FastAPI
# from src.services.auth_services import init_fief
from fastapi.middleware.cors import CORSMiddleware
# Environments
from dotenv import load_dotenv
# Services
from src.services.mqtt_services import fast_mqtt
# Entities
from src.entities.task_entity import task_expiration_manager
# Database
import src.services.database_services as database
# Routers
from src.routers.session_router import session_router
from src.routers.station_router import station_router
from src.routers.auth_router import auth_router
from src.routers.review_router import review_router
from src.routers.admin_router import admin_router
from src.routers.maintenance_router import maintenance_router
from src.routers.dashboard_router import dashboard_router

# Load environment variables
load_dotenv('.env')


@asynccontextmanager
async def _lifespan(_fastapi_app: FastAPI):
    """Context manager for the application lifespan"""
    await database.setup()
    await fast_mqtt.mqtt_startup()
    task_expiration_manager.restart()
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

# Attach the fief client to the app
# app.state.fief = init_fief()


# Include routers
app.include_router(station_router, prefix="/stations",
                   tags=["Station"])
app.include_router(session_router, prefix="/sessions",
                   tags=["Sessions"])
# app.include_router(user_router, prefix="/users", tags=["Users"])
app.include_router(maintenance_router, prefix='/maintenace',
                   tags=['Maintenance'])
app.include_router(auth_router, prefix='/auth',
                   tags=['Authentification'])
app.include_router(review_router, prefix='/review',
                   tags=['Reviews'])
app.include_router(admin_router, prefix='/admin',
                   tags=['Admin'])
app.include_router(dashboard_router, prefix='/dashboard',
                   tags=['Dashboard'])


if __name__ == "__main__":
    # os.system('clear')
    # Run the server
    uvicorn.run("main:app", host="0.0.0.0", port=8080,
                reload=True, reload_dirs=['src'])
