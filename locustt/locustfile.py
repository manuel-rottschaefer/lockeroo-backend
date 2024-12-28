"""Locust configuration file for testing the Lockeroo Backend."""
from os import getenv

from dotenv import load_dotenv
from locust import HttpUser, TaskSet, between, task

from locustt.behaviors import (AbandonAfterCreate,
                               AbandonAfterPaymentSelection,
                               Abandon1stVerificationThenNormal,
                               AbandonDuringBothVerifications, RegularSession)

# Load environment variables
load_dotenv('environments/.env')


class SessionTaskSet(TaskSet):
    """TaskSet for regular session behavior"""
    @task(0)
    def regular_session_task(self):
        RegularSession(self, self.user).run()

    @task(0)
    def abandon_after_create_task(self):
        AbandonAfterCreate(self, self.user).run()

    @task(0)
    def abandon_after_payment_selection_task(self):
        AbandonAfterPaymentSelection(self, self.user).run()

    @task(80)
    def abandon_first_verification_then_normal_task(self):
        Abandon1stVerificationThenNormal(self, self.user).run()

    @task(80)
    def abandon_during_both_verifications_task(self):
        AbandonDuringBothVerifications(self, self.user).run()


class LockerStationUser(HttpUser):
    host = getenv('API_BASE_URL')
    tasks = {SessionTaskSet: 1}
    wait_time = between(15, 30)
