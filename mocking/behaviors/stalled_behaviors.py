"""Session behaviors that end in SessionState.STALE."""
from mocking.dep.abilities import MockingSession
from src.models.session_models import SessionState


class AbandonStashing(MockingSession):
    """Abandon session after stashing."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.user_request_verification()
        self.await_state(SessionState.VERIFICATION)
        self.delay_action(SessionState.VERIFICATION)

        self.station_report_verification()
        self.await_state(SessionState.STASHING)
        self.wait_for_timeout(SessionState.STASHING)

        self.verify_state(SessionState.STALE, final=True)


class AbandonRetrieval(MockingSession):
    """Abandon session after retrieval."""

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
        self.wait_for_timeout(SessionState.RETRIEVAL)

        self.verify_state(SessionState.STALE, final=True)


class AbandonAfterStashingCancel(MockingSession):
    """Abandon session after stashing and then cancel."""

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

        self.user_request_cancel_session()
        self.await_state(SessionState.CANCELED)
        self.delay_action(SessionState.STASHING)

        self.verify_state(SessionState.STALE, final=True)
