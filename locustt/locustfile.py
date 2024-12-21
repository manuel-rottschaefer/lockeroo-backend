"""Locust configuration file for testing the Lockeroo Backend."""
from dotenv import load_dotenv
from os import getenv


from locust import HttpUser, TaskSet, task, between

from locustt.behaviors import (
    RegularSession,
    AbandonAfterCreate,
    AbandonAfterPaymentSelection,
    AbandonDuring1stVerification,
    AbandonDuringBothVerifications
)

# Load environment variables
load_dotenv('./environments/.env')
load_dotenv('environments/quick.env')


class SessionTaskSet(TaskSet):
    """TaskSet for regular session behavior"""

    @task(90)
    def regular_session_task(self):
        RegularSession(self, self.user).run()

    @task(0)
    def abandon_after_create_task(self):
        AbandonAfterCreate(self, self.user).run()

    @task(0)
    def abandon_after_payment_selection_task(self):
        AbandonAfterPaymentSelection(self, self.user).run()

    @task(0)
    def abandon_during_first_verification_task(self):
        AbandonDuring1stVerification(self, self.user).run()

    @task(0)
    def abandon_during_both_verifications_task(self):
        AbandonDuringBothVerifications(self, self.user).run()


class LockerStationUser(HttpUser):
    host = getenv('API_BASE_URL')
    tasks = {SessionTaskSet: 1}
    wait_time = between(15, 30)
