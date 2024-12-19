"""This module contains method to emulate station actions, but initiated by the user."""


def report_verification(logger, mqtt, callsign: str):
    '''Put the terminal into idle mode'''
    logger.debug(f"Reporting verification at station '{callsign}'.")
    mqtt.publish(
        f'stations/{callsign}/verification/report', '123456', qos=1)


def report_payment(logger, mqtt, callsign: str):
    '''Report a payment event to the backend'''
    logger.debug(f"Reporting payment at station '{callsign}'.")
    mqtt.publish(
        f'stations/{callsign}/payment/report', '123456', qos=1)


def report_locker_open(logger, mqtt, callsign: str, locker_number: int):
    '''Open a locker at the station'''
    logger.debug(f"Opening locker {locker_number} at station '{callsign}'.")
    mqtt.publish(
        f'stations/{callsign}/locker/{locker_number}/report', 'UNLOCKED', qos=1)


def report_locker_close(logger, mqtt, callsign: str, locker_number: int):
    '''Open a locker at the station'''
    logger.debug(f"Closing locker {locker_number} at station '{callsign}'.")
    logger.debug(
        f'stations/{callsign}/locker/{locker_number}/report' + 'LOCKED')
    mqtt.publish(
        f'stations/{callsign}/locker/{locker_number}/report', 'LOCKED', qos=1)
