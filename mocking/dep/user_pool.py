"""This module provides a UserPool class that locust can use to manage user IDs"""
from uuid import uuid4
# from mocking.dep.mocking_logger import logger


class UserPool():
    """Provides locust with user IDs"""

    def __init__(self):
        self.userbase = [str(uuid4()) for _ in range(20)]
        self.available_users = self.userbase.copy()

    def pick_user(self):
        if len(self.available_users) == 0:
            return None
        user = self.available_users.pop()
        return user

    def drop_user(self, user_id: uuid4):
        self.available_users.append(user_id)
