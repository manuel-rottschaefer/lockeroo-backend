"""This module contains method to emulate station actions, but initiated by the user."""
from paho.mqtt.client import Client


def report_verification(logger, mqtt: Client, callsign: str):
    '''Put the terminal into idle mode'''
    logger.debug(f"Reporting verification at station '{callsign}'.")
    try:
        mqtt.publish(
            f'stations/{callsign}/verification/report', '123456', qos=2)
        logger.info(f"Verification reported at station '{callsign}'.")
    except Exception as e:
        logger.error(f"Failed to report verification at station '{
                     callsign}': {e}")


def report_payment(logger, mqtt: Client, callsign: str):
    '''Report a payment event to the backend'''
    logger.debug(f"Reporting payment at station '{callsign}'.")
    try:
        mqtt.publish(
            f'stations/{callsign}/payment/report', '123456', qos=2)
        logger.info(f"Payment reported at station '{callsign}'.")
    except Exception as e:
        logger.error(f"Failed to report payment at station '{callsign}': {e}")


def report_locker_open(logger, mqtt: Client, callsign: str, locker_number: int):
    '''Open a locker at the station'''
    logger.debug(f"Opening locker {locker_number} at station '{callsign}'.")
    try:
        mqtt.publish(
            f'stations/{callsign}/locker/{locker_number}/report', 'UNLOCKED', qos=2)
        logger.info(f"Locker {locker_number} opened at station '{callsign}'.")
    except Exception as e:
        logger.error(f"Failed to open locker {
                     locker_number} at station '{callsign}': {e}")


def report_locker_close(logger, mqtt: Client, callsign: str, locker_number: int):
    '''Open a locker at the station'''
    logger.debug(f"Closing locker {locker_number} at station '{callsign}'.")
    try:
        mqtt.publish(
            f'stations/{callsign}/locker/{locker_number}/report', 'LOCKED', qos=2)
        logger.info(f"Locker {locker_number} closed at station '{callsign}'.")
    except Exception as e:
        logger.error(f"Failed to close locker {
                     locker_number} at station '{callsign}': {e}")
