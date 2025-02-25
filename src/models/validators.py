"""Validator for all models in the models folder"""
from pydantic import BeforeValidator
from typing import Annotated
import random
import datetime
import time


PyObjectId = Annotated[str, BeforeValidator(str)]


def random_timestamp():
    """Generates a random timestamp (datetime object)."""

    # Generate a random number of seconds since the epoch (Jan 1, 1970).
    random_seconds = random.randint(0, int(time.time()))  # up to current time

    # Convert the random seconds to a datetime object.
    random_datetime = datetime.datetime.fromtimestamp(random_seconds)

    return random_datetime
