# Beanie
from beanie.operators import In
# Entities
from src.entities.user_entity import User
# Models
from src.models.session_models import ACTIVE_SESSION_STATES, SessionModel
from src.models.permission_models import PERMISSION
# Services
from src.services.auth_services import permission_check


async def get_active_session_count(user: User):
    """Get the amount of currently active sessions."""
    # 1: Check permissions
    permission_check([PERMISSION.FIEF_ADMIN], user.doc.permissions)

    # 2: Return active session count
    return await SessionModel.find(
        In(SessionModel.session_state, ACTIVE_SESSION_STATES),
    ).to_list()
