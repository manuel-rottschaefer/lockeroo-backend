"""Session behaviors that are just wrong."""
from mocking.dep.abilities import MockingSession
from src.models.session_models import SessionState, PaymentMethod


class EarlyVerificationReport(MockingSession):
    """Report verification before it is requested."""

    def run(self, terminate: bool = True):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.stripe_report_verification(expected_code=400)
        self.verify_state(SessionState.TERMINATED, terminate)


class EarlyPaymentReport(MockingSession):
    """Report payment before it is selected."""

    def run(self, terminate: bool = True):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.stripe_report_payment(expected_code=400)
        self.verify_state(SessionState.TERMINATED, terminate)


class HoldTerminalSession(MockingSession):
    """Hold a session of type terminal which cannot be paused."""

    def run(self, terminate: bool = True):  # pylint: disable=missing-function-docstring
        self.set_payment_method(PaymentMethod.TERMINAL)
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

        self.user_request_hold(expected_code=400)
        self.verify_state(SessionState.TERMINATED, terminate)
