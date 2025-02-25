"""Session behaviors that end in SessionState.CANCELED."""
from mocking.dep.abilities import MockingSession
from src.models.session_models import SessionState


class CancelAfterCreate(MockingSession):
    """Cancel session after creation."""

    def run(self, terminate: bool = True):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.user_request_cancel_session()
        self.verify_state(SessionState.CANCELED, terminate)


class CancelAfterPaymentSelection(MockingSession):
    """Cancel session after payment selection."""

    def run(self, terminate: bool = True):  # pylint: disable=missing-function-docstring
        self.user_request_session(select_payment=False)
        self.verify_state(SessionState.CREATED)
        self.delay_action(SessionState.CREATED)

        self.user_select_payment_method()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.user_request_cancel_session()
        self.verify_state(SessionState.CANCELED, terminate)


class CancelDuringVerification(MockingSession):
    """Cancel session during verification."""

    def run(self, terminate: bool = True):  # pylint: disable=missing-function-docstring
        self.user_request_session()
        self.verify_state(SessionState.PAYMENT_SELECTED)
        self.delay_action(SessionState.PAYMENT_SELECTED)

        self.user_request_verification()
        self.await_state(SessionState.VERIFICATION)
        self.delay_action(SessionState.VERIFICATION)

        self.user_request_cancel_session()
        self.verify_state(SessionState.CANCELED, terminate)


class CancelDuringStashing(MockingSession):
    """Cancel session during stashing."""

    def run(self, terminate: bool = True):  # pylint: disable=missing-function-docstring
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
        self.verify_state(SessionState.CANCELED)
        self.delay_action(SessionState.CANCELED)

        self.station_report_locker_close()
        self.verify_state(SessionState.CANCELED, terminate)
