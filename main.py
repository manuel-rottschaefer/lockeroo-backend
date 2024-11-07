'''Main backend file'''

# Standard imports
from contextlib import asynccontextmanager

# API services
import uvicorn
from fastapi import FastAPI, Depends
from fastapi.security import HTTPBearer

# Fief
from fastapi.security import OAuth2AuthorizationCodeBearer
from fief_client import FiefAccessTokenInfo, FiefAsync
from fief_client.integrations.fastapi import FiefAuth

# Environments
from dotenv import load_dotenv

# MQTT
from src.services.mqtt_services import fast_mqtt

# Database
import src.database.db as database

# Routers
from src.routers.account_router import accountRouter
from src.routers.session_router import sessionRouter
from src.routers.station_router import stationRouter

fief = FiefAsync(
    "localhost:8000",
    "Xhs42xN0ZQg4JI1HYJHb397rxVS8hmIS4yVGC5cl6b0",
    "iIzvxunju2_enh3ixeTPlAh3YK3uw2Ga2eGF57Qc3kc",
)

scheme = OAuth2AuthorizationCodeBearer(
    "localhost:8000/authorize",
    "localhost:8000/api/token",
    scopes={"openid": "openid", "offline_access": "offline_access"},
    auto_error=False,
)

auth = FiefAuth(fief, scheme)


@asynccontextmanager
async def _lifespan(_fastapi_app: FastAPI):
    '''Context manager for the application lifespan'''
    load_dotenv(dotenv_path='environments/.env')
    await database.setup()
    await fast_mqtt.mqtt_startup()
    # Wait until server shutdown
    yield
    await fast_mqtt.mqtt_shutdown()


# Create app
app = FastAPI(lifespan=_lifespan)

# Set up auth
token_auth_scheme = HTTPBearer()

# Include routers
app.include_router(stationRouter, prefix="/stations", tags=["Stations"])
app.include_router(sessionRouter, prefix="/sessions", tags=["Sessions"])
app.include_router(accountRouter, prefix="/account", tags=["Account"])


@app.get("/user")
async def get_user(
    access_token_info: FiefAccessTokenInfo = Depends(auth.authenticated()),
):
    '''Just for debugging.'''
    return access_token_info


if __name__ == "__main__":
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=80, reload=True, log_config=None)
