
from locustt.delays import ACTION_DELAYS
from locustt.locust_session import LocustSession
from src.models.session_models import SESSION_TIMEOUTS, SessionState


class RegularSession(LocustSession):
    """Run a regular session."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(ACTION_DELAYS[SessionState.CREATED])
        self.subscribe_to_updates()

        self.session = self.user_select_payment_method()
        self.delay_session(ACTION_DELAYS[SessionState.PAYMENT_SELECTED])

        self.session = self.user_request_verification()
        self.await_session_state(SessionState.VERIFICATION)
        self.delay_session(ACTION_DELAYS[SessionState.VERIFICATION])

        self.station_report_verification()
        self.await_session_state(SessionState.STASHING)
        self.delay_session(ACTION_DELAYS[SessionState.STASHING])

        self.station_report_locker_close()
        self.await_session_state(SessionState.ACTIVE)
        self.delay_session(ACTION_DELAYS[SessionState.ACTIVE])

        self.session = self.request_payment()
        self.await_session_state(SessionState.PAYMENT)
        self.delay_session(ACTION_DELAYS[SessionState.PAYMENT])

        self.station_report_payment()
        self.await_session_state(SessionState.RETRIEVAL)
        self.delay_session(ACTION_DELAYS[SessionState.RETRIEVAL])

        self.station_report_locker_close()
        self.await_session_state(SessionState.COMPLETED)
        self.terminate_session()


class AbandonAfterCreate(LocustSession):
    """Abandon session after creation."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(SESSION_TIMEOUTS[SessionState.CREATED] + 1)
        self.verify_session_state(SessionState.EXPIRED)
        self.terminate_session()


class AbandonAfterPaymentSelection(LocustSession):
    """Abandon session after payment selection."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        # Delay until selection of payment method
        self.delay_session(ACTION_DELAYS[SessionState.CREATED])
        self.session = self.user_select_payment_method()

        self.delay_session(SESSION_TIMEOUTS[SessionState.PAYMENT_SELECTED] + 1)
        self.verify_session_state(SessionState.EXPIRED)
        self.terminate_session()


class Abandon1stVerificationThenNormal(LocustSession):
    """Miss the first verification window, but then continue as normal."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(ACTION_DELAYS[SessionState.CREATED])
        self.subscribe_to_updates()
        # Pause until selection of payment method
        self.session = self.user_select_payment_method()
        self.delay_session(ACTION_DELAYS[SessionState.PAYMENT_SELECTED])
        # Request verification, then await verification
        self.session = self.user_request_verification()
        self.await_session_state(SessionState.VERIFICATION)
        # Delay until verification window expires
        self.delay_session(SESSION_TIMEOUTS[SessionState.VERIFICATION] + 1)
        self.verify_session_state(SessionState.PAYMENT_SELECTED)
        # Request verification again, then await verification
        self.delay_session(ACTION_DELAYS[SessionState.PAYMENT_SELECTED])
        self.session = self.user_request_verification()
        self.await_session_state(SessionState.VERIFICATION)
        self.delay_session(ACTION_DELAYS[SessionState.VERIFICATION])
        # Continue with the session
        self.station_report_verification()
        self.await_session_state(SessionState.STASHING)
        self.delay_session(ACTION_DELAYS[SessionState.STASHING])

        self.station_report_locker_close()
        self.await_session_state(SessionState.ACTIVE)
        self.delay_session(ACTION_DELAYS[SessionState.ACTIVE])

        self.session = self.request_payment()
        self.await_session_state(SessionState.PAYMENT)
        self.delay_session(ACTION_DELAYS[SessionState.PAYMENT])

        self.station_report_payment()
        self.await_session_state(SessionState.RETRIEVAL)
        self.delay_session(ACTION_DELAYS[SessionState.RETRIEVAL])

        self.station_report_locker_close()
        self.await_session_state(SessionState.COMPLETED)
        self.terminate_session()


class AbandonDuringBothVerifications(LocustSession):
    """Miss the verification time windows 2 times."""

    def run(self):  # pylint: disable=missing-function-docstring
        self.session = self.user_request_session()
        self.delay_session(ACTION_DELAYS[SessionState.CREATED])
        self.subscribe_to_updates()
        # Pause until selection of payment method
        self.session = self.user_select_payment_method()
        self.delay_session(ACTION_DELAYS[SessionState.PAYMENT_SELECTED])
        # Request verification, then await verification
        self.session = self.user_request_verification()
        self.await_session_state(SessionState.VERIFICATION)
        # Delay until verification window expires
        self.delay_session(SESSION_TIMEOUTS[SessionState.VERIFICATION] + 1)
        self.verify_session_state(SessionState.PAYMENT_SELECTED)
        self.delay_session(ACTION_DELAYS[SessionState.PAYMENT_SELECTED])
        # Request verification again, then await verification
        self.session = self.user_request_verification()
        self.await_session_state(SessionState.VERIFICATION)
        # Delay until verification window expires again
        self.delay_session(SESSION_TIMEOUTS[SessionState.VERIFICATION] + 1)
        self.verify_session_state(SessionState.EXPIRED)
        self.terminate_session()
