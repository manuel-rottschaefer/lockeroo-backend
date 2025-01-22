"""Validator for all models in the models folder"""
# Types
from typing import Annotated
# Pydantic
from pydantic import BeforeValidator


PyObjectId = Annotated[str, BeforeValidator(str)]
