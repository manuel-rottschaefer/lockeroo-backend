"""Session behaviors that are just wrong."""
from mocking.dep.abilities import MockingSession
from src.models.session_models import SessionState


class EarlyVerificationReport(MockingSession):
    """Report verification before it is requested."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.CREATED)
        self.delay_action(SessionState.CREATED)

        self.stripe_report_verification(expected_code=400)
        self.verify_state(SessionState.TERMINATED, final=True)


class EarlyPaymentReport(MockingSession):
    """Report payment before it is selected."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.CREATED)
        self.delay_action(SessionState.CREATED)

        self.stripe_report_payment(expected_code=400)
        self.verify_state(SessionState.TERMINATED, final=True)
