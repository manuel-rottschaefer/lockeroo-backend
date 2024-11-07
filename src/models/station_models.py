'''
Station Models
'''

# Types
from enum import Enum
import dataclasses
from datetime import datetime
from typing import Optional, Tuple, Dict
from pydantic import Field

# Beanie
from beanie import Document, View, Replace, after_event
from beanie import PydanticObjectId as ObjId

# Services
from ..services.mqtt_services import fast_mqtt


class StationStates(str, Enum):
    '''States for a station'''

    AVAILABLE = "available"  # Station terminal is passive and waiting for sessions
    MAINTENANCE = "maintenance"  # Station terminal is offline for maintenance
    OUTOFSERVICE = "outOfService"  # Station terminal is offline and awaiting repair


class TerminalStates(str, Enum):
    '''States for a terminal'''

    IDLE = "idle"  # Terminal is idle
    VERIFICATION = "verification"  # Terminal is in verification mode
    PAYMENT = "payment"  # Terminal is in payment mode
    OUTOFSERVICE = "outOfService"  # Terminal is offline or awaiting repair


class StationModel(Document):  # pylint: disable=too-many-ancestors
    '''Representation of a station in the database'''

    # Identification
    id: Optional[ObjId] = Field(None, alias="_id")
    full_name: str
    call_sign: str

    # Authentification
    secret: str = ""

    # Internal Properties
    station_type: str
    hw_version: str
    sw_version: str

    # Setup and Installation Data
    installation_ts: datetime
    installed_lockers: int

    # Operation state
    station_state: StationStates = Field(default=StationStates.AVAILABLE)
    terminal_state: TerminalStates = Field(default=TerminalStates.IDLE)
    next_service_date: datetime
    service_due: bool

    # Operation history
    total_sessions: int
    total_session_duration: int
    last_service_date: datetime

    # Service states
    is_storage_available: bool
    is_charging_available: bool

    # Location
    city_name: str
    address: str
    location: Dict
    nearby_public_transit: Optional[str]

    @after_event(Replace)
    def notify_station_state(self):
        '''Send an update message regarding the session state to the mqtt broker.'''
        fast_mqtt.publish(
            f"stations/{self.id}/state", self.station_state.value)

    ### State broadcasting ###
    @after_event(Replace)
    def notify_terminal_state(self):
        '''Send an update message regarding the session state to the mqtt broker.'''
        fast_mqtt.publish(
            f"stations/{self.id}/terminal", self.terminal_state.value)

    @dataclasses.dataclass
    class Settings:
        '''Name in database'''

        name = "stations"


class StationView(View):
    '''Public representation of a station'''

    # Identification
    id: Optional[ObjId] = Field(None, alias="_id")
    full_name: str
    call_sign: str

    # Internal Properties
    station_type: str

    # Setup and Installation Data
    installed_lockers_count: int

    # Operation states
    station_state: StationStates

    is_storage_available: bool
    is_charging_available: bool

    # Location
    city_name: str
    address: str
    geolocation: Tuple[float, float]
    nearby_public_transit: Optional[str]

    async def get_locker_availability(self, station_services):
        '''Get the availability of lockers at the station'''
        return await station_services.get_locker_availability(self)


class StationLockers(View):
    '''Availability of each locker type at a station'''

    small: bool
    medium: bool
    large: bool


class StationMaintenanceStates(str, Enum):
    '''All possible states of a station maintenance event'''

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    ISSUE = "issue"
    CANCELED = "canceled"


class StationMaintenance(Document):  # pylint: disable=too-many-ancestors
    '''Entity of a station mainentance event'''

    id: Optional[ObjId] = Field(None, alias="_id")

    assigned_station: ObjId = Field(
        "Station to which this maintenance is assigned to")

    scheduled: datetime = Field(description="Scheduled time of maintenance")
    started: Optional[datetime] = Field(description="Actual starting time")
    completed: Optional[datetime] = Field(
        description="Actual completition time")

    state: StationMaintenanceStates = Field(
        description="Current state of the maintenance item"
    )

    assigned_person: str = Field(
        default="", description="The person assigned with this task"
    )

    class Settings:
        '''Name in Database'''

        name = "maintenance"
