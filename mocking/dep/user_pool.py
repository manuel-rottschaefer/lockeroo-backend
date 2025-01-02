"""This module provides a UserPool class that locust can use to manage user IDs"""
from uuid import uuid4
# from mocking.dep.mocking_logger import logger


class UserPool():
    """Provides locust with user IDs"""

    def __init__(self):
        self.userbase = [str(uuid4()) for _ in range(20)]
        self.available_users = self.userbase.copy()

    def get_available_user(self):
        if len(self.available_users) == 0:
            return None
        user = self.available_users.pop()
        # logger.debug(f"User {user} retrieved from available users.")
        return user

    def return_user(self, user_id: uuid4):
        self.available_users.append(user_id)
        # logger.debug(f"Users available: {len(self.available_users)}")
        # logger.debug(f"User {user_id} returned to available users.")
