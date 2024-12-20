"""
Methods to call HTTP endpoints or sent/retrieve data over MQTT or Websockets.
These methods should receive all data as parameters and not over any class relations.
"""
from src.models.session_models import SessionView
import websockets.sync.client as websockets
from typing import Optional


def create_session(
        task_set,
        station_callsign: str,
        locker_type: str) -> Optional[SessionView]:
    """Try to request a new session at the locker station."""
    task_set.logger.debug(f"Creating session at station '{
                          station_callsign}' and with {locker_type}.")
    res = task_set.client.post(
        task_set.endpoint + '/sessions/create', params={
            'station_callsign': station_callsign,
            'locker_type': locker_type
        }, headers=task_set.headers, timeout=3)
    if res.status_code == 400:
        return None
    res.raise_for_status()
    session: SessionView = SessionView(**res.json())
    return session


def cancel_session(
        task_set,
        session_id: str) -> Optional[SessionView]:
    """Try to cancel a session."""
    task_set.logger.debug(f"Cancelling session {session_id}'.")
    res = task_set.client.put(
        task_set.endpoint + f"/sessions/{session_id}/cancel", params={
            'session_id': session_id
        }, headers=task_set.headers, timeout=3)
    if res.status_code == 400:
        return None
    res.raise_for_status()
    return SessionView(**res.json())


def select_payment_method(
        task_set,
        session_id: str,
        payment_method: str) -> Optional[SessionView]:
    """Try to select a payment method for a session."""
    task_set.logger.debug(f"Selecting payment method {
                          payment_method} for session '#{session_id}'.")
    res = task_set.client.put(
        task_set.endpoint + f'/sessions/{session_id}/payment/select', params={
            'payment_method': payment_method
        }, headers=task_set.headers, timeout=3)
    if res.status_code == 400:
        return None
    res.raise_for_status()
    return SessionView(**res.json())


def request_verification(
        task_set,
        session_id: str) -> Optional[SessionView]:
    """Try to request verification for a session."""
    task_set.logger.debug(
        f"Requesting verification for session '#{session_id}'.")
    res = task_set.client.put(
        task_set.endpoint + f"/sessions/{session_id}/payment/verify",
        headers=task_set.headers, timeout=3)
    if res.status_code == 400:
        return None
    res.raise_for_status()
    return SessionView(**res.json())


def request_hold(
        task_set,
        session_id: str) -> Optional[SessionView]:
    """Try to request a hold for a session."""
    task_set.logger.debug(f"Requesting hold for session '#{session_id}'.")
    res = task_set.client.put(
        task_set.endpoint + f"/sessions/{session_id}/hold",
        headers=task_set.headers, timeout=3)
    if res.status_code == 400:
        return None
    res.raise_for_status()
    return SessionView(**res.json())


def request_payment(
        task_set,
        session_id: str) -> Optional[SessionView]:
    """Try to request payment for a session."""
    task_set.logger.debug(f"Requesting payment for session '#{session_id}'.")
    res = task_set.client.put(
        task_set.endpoint + f"/sessions/{session_id}/payment",
        headers=task_set.headers, timeout=3)
    if res.status_code == 400:
        return None
    res.raise_for_status()
    return SessionView(**res.json())


def await_websocket_state(
        task_set,
        ws_endpoint: str,
        session_id: str,
        desired_state: str):
    """Await backend response to begin stashing."""
    ws_url = ws_endpoint + f'/sessions/{session_id}/subscribe'
    task_set.logger.debug(
        (f"Connecting to update stream for session '#{session_id}' "
         f"and awaiting state {desired_state}"))
    with websockets.connect(ws_url) as ws:
        while True:
            message = ws.recv().lower()
            if message == desired_state.lower():
                task_set.logger.debug(
                    (f"Reached state {desired_state} for session '#{session_id}'."))
                ws.close()
                return message
