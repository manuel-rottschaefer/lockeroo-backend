"""Session behaviors that end in SessionState.COMPLETED."""
from mocking.dep.abilities import MockingSession
from src.models.session_models import SessionState


class RegularSession(MockingSession):
    """Run a regular session.
    A block in a behaviour should always follow the following pattern:
    1. Send request
    2. Await or verify session state
    3. (Other actions)
    4. Delay or wait for timeout
    """

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
        self.delay_action(SessionState.PAYMENT)

        self.station_report_payment()
        self.await_state(SessionState.RETRIEVAL)
        self.delay_action(SessionState.RETRIEVAL)

        self.station_report_locker_close()
        self.await_state(SessionState.COMPLETED)
        self.verify_state(SessionState.COMPLETED, final=True)


class Abandon1stVerifyThenNormal(MockingSession):
    """Miss the first verification window, but then continue as normal."""

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
        self.delay_action(SessionState.VERIFICATION)

        self.station_report_verification()
        self.await_state(SessionState.STASHING)
        self.delay_action(SessionState.STASHING)

        self.station_report_locker_close()
        self.await_state(SessionState.ACTIVE)
        self.delay_action(SessionState.ACTIVE)

        self.user_request_payment()
        self.await_state(SessionState.PAYMENT)
        self.delay_action(SessionState.PAYMENT)

        self.station_report_payment()
        self.await_state(SessionState.RETRIEVAL)
        self.delay_action(SessionState.RETRIEVAL)

        self.station_report_locker_close()
        self.await_state(SessionState.COMPLETED)
        self.verify_state(SessionState.COMPLETED, final=True)


class Abandon1stPaymentThenNormal(MockingSession):
    """Miss the first payment window, but then continue as normal."""

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
        self.delay_action(SessionState.PAYMENT)

        self.station_report_payment()
        self.await_state(SessionState.RETRIEVAL)
        self.delay_action(SessionState.RETRIEVAL)

        self.station_report_locker_close()
        self.await_state(SessionState.COMPLETED)
        self.verify_state(SessionState.COMPLETED, final=True)
