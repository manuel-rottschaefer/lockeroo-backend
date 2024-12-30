"""Validator for all models in the models folder"""
# Types
from typing import Annotated
# Pydantic
from pydantic import BeforeValidator, ValidationError


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
    """Validate all models in the models folder"""
    models = []
    for model in models:
        test_model(model)


PyObjectId = Annotated[str, BeforeValidator(str)]
