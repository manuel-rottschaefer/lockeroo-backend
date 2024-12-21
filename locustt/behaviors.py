
from locustt.locust_session import LocustSession
from locustt.delays import ACTION_DELAYS
from src.models.session_models import SessionStates, SESSION_TIMEOUTS


class RegularSession(LocustSession):
    """Run a regular session."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(ACTION_DELAYS[SessionStates.CREATED])
        self.subscribe_to_updates()

        self.session = self.user_select_payment_method()
        self.delay_session(ACTION_DELAYS[SessionStates.PAYMENT_SELECTED])

        self.session = self.user_request_verification()
        self.await_session_state(SessionStates.VERIFICATION)
        self.delay_session(ACTION_DELAYS[SessionStates.VERIFICATION])

        self.station_report_verification()
        self.await_session_state(SessionStates.STASHING)
        self.delay_session(ACTION_DELAYS[SessionStates.STASHING])

        self.report_locker_close()
        self.await_session_state(SessionStates.ACTIVE)
        self.delay_session(ACTION_DELAYS[SessionStates.ACTIVE])

        self.session = self.request_payment()
        self.await_session_state(SessionStates.PAYMENT)
        self.delay_session(ACTION_DELAYS[SessionStates.PAYMENT])

        self.report_payment()
        self.await_session_state(SessionStates.RETRIEVAL)
        self.delay_session(ACTION_DELAYS[SessionStates.RETRIEVAL])

        self.report_locker_close()
        self.await_session_state(SessionStates.COMPLETED)
        self.terminate_session()


class AbandonAfterCreate(LocustSession):
    """Abandon session after creation."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(SESSION_TIMEOUTS[SessionStates.CREATED])
        self.verify_session_state(SessionStates.EXPIRED)
        self.terminate_session()


class AbandonAfterPaymentSelection(LocustSession):
    """Abandon session after payment selection."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(ACTION_DELAYS[SessionStates.CREATED])

        self.session = self.user_select_payment_method()
        self.delay_session(SESSION_TIMEOUTS[SessionStates.PAYMENT_SELECTED])
        self.verify_session_state(SessionStates.EXPIRED)
        self.terminate_session()


class AbandonDuring1stVerification(LocustSession):
    """Miss the first verification window, but then continue as normal."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(ACTION_DELAYS[SessionStates.CREATED])
        self.subscribe_to_updates()

        self.session = self.user_select_payment_method()
        self.delay_session(ACTION_DELAYS[SessionStates.PAYMENT_SELECTED])

        self.session = self.user_request_verification()
        self.await_session_state(SessionStates.VERIFICATION)
        self.delay_session(SESSION_TIMEOUTS[SessionStates.VERIFICATION])
        self.verify_session_state(SessionStates.PAYMENT_SELECTED)

        self.session = self.user_request_verification()
        self.await_session_state(SessionStates.VERIFICATION)
        self.delay_session(ACTION_DELAYS[SessionStates.VERIFICATION])

        self.station_report_verification()
        self.await_session_state(SessionStates.STASHING)
        self.delay_session(ACTION_DELAYS[SessionStates.STASHING])

        self.report_locker_close()
        self.await_session_state(SessionStates.ACTIVE)
        self.delay_session(ACTION_DELAYS[SessionStates.ACTIVE])

        self.session = self.request_payment()
        self.await_session_state(SessionStates.PAYMENT)
        self.delay_session(ACTION_DELAYS[SessionStates.PAYMENT])

        self.report_payment()
        self.await_session_state(SessionStates.RETRIEVAL)
        self.delay_session(ACTION_DELAYS[SessionStates.RETRIEVAL])

        self.report_locker_close()
        self.await_session_state(SessionStates.COMPLETED)
        self.terminate_session()


class AbandonDuringBothVerifications(LocustSession):
    """Miss the verification time windows 2 times."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(ACTION_DELAYS[SessionStates.CREATED])
        self.subscribe_to_updates()

        self.session = self.user_select_payment_method()
        self.delay_session(ACTION_DELAYS[SessionStates.PAYMENT_SELECTED])

        self.session = self.user_request_verification()
        self.await_session_state(SessionStates.VERIFICATION)
        self.delay_session(SESSION_TIMEOUTS[SessionStates.VERIFICATION])

        self.session = self.user_request_verification()
        self.await_session_state(SessionStates.VERIFICATION)
        self.delay_session(SESSION_TIMEOUTS[SessionStates.VERIFICATION])

        self.verify_session_state(SessionStates.EXPIRED)
        self.terminate_session()
