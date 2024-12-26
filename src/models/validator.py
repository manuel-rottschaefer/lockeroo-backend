"""Validator for all models in the models folder"""
from pydantic import ValidationError

from src.models.action_models import ActionModel, ActionView
from src.models.billing_models import BillModel
from src.models.locker_models import LockerModel, LockerView
from src.models.maintenance_models import MaintenanceModel, MaintenanceView
from src.models.payment_models import PaymentModel
from src.models.review_models import ReviewModel, ReviewView
from src.models.session_models import SessionModel, SessionView
from src.models.station_models import StationModel, StationView
from src.models.task_models import TaskItemModel
from src.models.user_models import UserModel, UserSummary


models = [ActionModel, ActionView,
          BillModel,
          LockerModel, LockerView,
          MaintenanceModel, MaintenanceView,
          PaymentModel,
          ReviewModel, ReviewView,
          SessionModel, SessionView,
          StationModel, StationView,
          TaskItemModel,
          UserModel, UserSummary]


def test_model(model_class):
    """Test the validation of a model"""
    try:
        example_data = model_class.Config.json_schema_extra
        _model_instance = model_class(**example_data)
        print(f"{model_class.__name__} is valid")
    except ValidationError as e:
        print(f"{model_class.__name__} validation error: {e}")
    except AttributeError:
        print(f"{model_class.__name__} does not have example data")


def validate():
    for model in models:
        test_model(model)
