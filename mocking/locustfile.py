"""Locust configuration file for testing the Lockeroo Backend."""

from os import getenv
from locust import HttpUser,  TaskSet, SequentialTaskSet, between, task


from mocking.behaviors import (
    success_behaviors,
    expired_behaviors,
    canceled_behaviors,
    stalled_behaviors)


class RandomizedBehaviors(TaskSet):
    """TaskSet for regular session behavior"""

    ### Success Behaviors ###
    @ task(700)
    def regular_session(self):
        success_behaviors.RegularSession(self, self.user).run()

    @ task(2)
    def abandon_first_verification_then_normal(self):
        success_behaviors.Abandon1stVerifyThenNormal(
            self, self.user).run()

    @ task(2)
    def abandon_first_payment_then_normal(self):
        success_behaviors.Abandon1stPaymentThenNormal(self, self.user).run()

    @ task(2)
    def hold_then_normal(self):
        success_behaviors.HoldThenNormal(self, self.user).run()

    @ task(2)
    def hold_then_payment(self):
        success_behaviors.HoldThenPayment(self, self.user).run()

    ### Expired Behaviors ###

    @ task(2)
    def abandon_reservation(self):
        expired_behaviors.AbandonReservation(self, self.user).run()

    @ task(2)
    def abandon_after_create(self):
        expired_behaviors.AbandonAfterCreate(self, self.user).run()

    @ task(2)
    def abandon_after_payment_selection(self):
        expired_behaviors.AbandonAfterPaymentSelection(self, self.user).run()

    @ task(2)
    def abandon_during_both_verifications(self):
        expired_behaviors.AbandonBothVerifications(self, self.user).run()

    @ task(2)
    def abandon_during_active(self):
        expired_behaviors.AbandonActive(self, self.user).run()

    @ task(2)
    def abandon_during_both_payments(self):
        expired_behaviors.AbandonBothPayments(self, self.user).run()

    ### Canceled Behaviors ###
    @ task(1)
    def cancel_after_create(self):
        canceled_behaviors.CancelAfterCreate(self, self.user).run()

    @ task(1)
    def cancel_after_payment_selection(self):
        canceled_behaviors.CancelAfterPaymentSelection(self, self.user).run()

    @ task(1)
    def cancel_during_verification(self):
        canceled_behaviors.CancelDuringVerification(self, self.user).run()

    @ task(1)
    def cancel_during_stashing(self):
        canceled_behaviors.CancelDuringStashing(self, self.user).run()

    ### Stalled Behaviors ###
    @ task(2)
    def abandon_stashing(self):
        stalled_behaviors.AbandonStashing(self, self.user).run()

    @ task(2)
    def abandon_hold(self):
        stalled_behaviors.AbandonHold(self, self.user).run()

    @ task(2)
    def abandon_retrieval(self):
        stalled_behaviors.AbandonRetrieval(self, self.user).run()


class UnitTestBehaviors(SequentialTaskSet):
    """Testing all behaviors once as unit tests"""

    @ task
    def test_all_session_behaviors(self):
        """Test all session behaviors"""
        ### Success Behaviors ###
        success_behaviors.RegularSession(self, self.user).run()
        success_behaviors.Abandon1stVerifyThenNormal(self, self.user).run()
        success_behaviors.Abandon1stPaymentThenNormal(self, self.user).run()

        ### Expired Behaviors ###
        expired_behaviors.AbandonAfterCreate(self, self.user).run()
        expired_behaviors.AbandonAfterPaymentSelection(self, self.user).run()
        expired_behaviors.AbandonBothVerifications(self, self.user).run()
        expired_behaviors.AbandonActive(self, self.user).run()
        expired_behaviors.AbandonBothPayments(self, self.user).run()

        ### Canceled Behaviors ###
        canceled_behaviors.CancelAfterCreate(self, self.user).run()
        canceled_behaviors.CancelAfterPaymentSelection(self, self.user).run()
        canceled_behaviors.CancelDuringVerification(self, self.user).run()
        canceled_behaviors.CancelDuringStashing(self, self.user).run()

        ### Stalled Behaviors ###
        stalled_behaviors.AbandonStashing(self, self.user).run()
        stalled_behaviors.AbandonRetrieval(self, self.user).run()


class LockerStationUser(HttpUser):
    host = getenv('API_BASE_URL')
    tasks = {RandomizedBehaviors: 1}  # RandomizedBehaviors: 1}
    wait_time = between(15, 30)
