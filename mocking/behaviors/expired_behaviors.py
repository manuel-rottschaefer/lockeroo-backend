"""Session behaviors that end in SessionState.EXPIRED."""
from mocking.dep.abilities import MockingSession
from src.models.session_models import SessionState


class AbandonReservation(MockingSession):
    """Request a session verification, then abandon the session."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_reservation()
        self.wait_for_timeout(SessionState.CREATED)

        self.verify_state(SessionState.EXPIRED, final=True)


class AbandonAfterCreate(MockingSession):
    """Abandon session after creation."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.wait_for_timeout(SessionState.PAYMENT_SELECTED)

        self.verify_state(SessionState.EXPIRED, final=True)


class AbandonAfterPaymentSelection(MockingSession):
    """Abandon session after payment selection."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_session(select_payment=False)
        self.verify_state(SessionState.CREATED)
        self.delay_action(SessionState.CREATED)

        self.user_select_payment_method()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.wait_for_timeout(SessionState.PAYMENT_SELECTED)

        self.verify_state(SessionState.EXPIRED, final=True)


class AbandonBothVerifications(MockingSession):
    """Miss the verification time windows 2 times."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.user_request_verification()
        self.await_state(SessionState.VERIFICATION)
        self.wait_for_timeout(SessionState.VERIFICATION)
        self.verify_state(SessionState.PAYMENT_SELECTED)

        self.user_request_verification()
        self.await_state(SessionState.VERIFICATION)
        self.wait_for_timeout(SessionState.VERIFICATION)
        self.verify_state(SessionState.EXPIRED, final=True)


class AbandonActive(MockingSession):
    """Abandon session after activation."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.user_request_verification()
        self.await_state(SessionState.VERIFICATION)
        self.delay_action(SessionState.VERIFICATION)

        self.station_report_verification()
        self.await_state(SessionState.STASHING)
        self.delay_action(SessionState.STASHING)

        self.station_report_locker_close()
        self.await_state(SessionState.ACTIVE)
        self.wait_for_timeout(SessionState.ACTIVE)

        self.verify_state(SessionState.ABANDONED, final=True)


class AbandonBothPayments(MockingSession):
    """Miss the payment time windows 2 times."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.user_request_verification()
        self.await_state(SessionState.VERIFICATION)
        self.delay_action(SessionState.VERIFICATION)

        self.station_report_verification()
        self.await_state(SessionState.STASHING)
        self.delay_action(SessionState.STASHING)

        self.station_report_locker_close()
        self.await_state(SessionState.ACTIVE)
        self.delay_action(SessionState.ACTIVE)

        self.user_request_payment()
        self.await_state(SessionState.PAYMENT)
        self.wait_for_timeout(SessionState.PAYMENT)
        self.verify_state(SessionState.ACTIVE)

        self.user_request_payment()
        self.await_state(SessionState.PAYMENT)
        self.wait_for_timeout(SessionState.PAYMENT)
        self.verify_state(SessionState.EXPIRED, final=True)
