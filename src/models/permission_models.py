# Types
from enum import Enum


class PERMISSION(str, Enum):
    """All possible types of session (services)"""
    FIEF_ADMIN = 'fief:admin'

    SESSION_VIEW_BASIC = 'session:view:basic'
    SESSION_ACT = 'session:act'

    STATION_VIEW_BASIC = 'station:view:basic'
    STATION_VIEW_ADVANCED = 'station:view:advanced'
    STATION_OPERATE = 'station:operate'

    MAINTENANCE_VIEW = 'maintenance:view'
    MAINTENANCE_CREATE = 'maintenance:create'
    MAINTENANCE_UPDATE = 'maintenance:update'
