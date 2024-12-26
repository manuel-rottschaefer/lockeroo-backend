""" Emulate a station """
import os
import re
import asyncio
import paho.mqtt.client as mqtt


def is_terminal_instruction(topic):
    pattern = r'^stations/[A-Z]{6}/terminal/instruct$'
    return re.match(pattern, topic) is not None


def is_locker_instruction(topic):
    pattern = r'^stations/[A-Z]{6}/locker/\d{1,2}/instruct$'
    return re.match(pattern, topic) is not None


def is_action_report(topic):
    pattern = r'^stations/[A-Z]{6}/(verification|payment|)/report$'
    return re.match(pattern, topic) is not None


def on_connect(_client, _userdata, _flags, _reason_code, _properties):
    '''The callback for when the client receives a CONNACK response from the server.'''
    # Station subscriptions
    mqttc.subscribe('stations/#')


async def on_message(_client, _userdata, msg: mqtt.MQTTMessage):
    '''The callback for when a PUBLISH message is received from the server.'''
    topic = msg.topic.split('/')
    payload = msg.payload.decode('utf-8')

    if is_terminal_instruction(msg.topic) and payload in ['VERIFICATION', 'PAYMENT', 'IDLE']:
        mqttc.publish(
            topic=f"stations/{msg.topic.split('/')[1]}/terminal/confirm",
            payload=payload,
            qos=2)
        print(f"Confirmed mode {payload} for station {
              msg.topic.split('/')[1]}.")
        await asyncio.sleep(0.1)  # Non-blocking delay

    elif is_locker_instruction(msg.topic) and payload in ['locked', 'unlocked']:
        mqttc.publish(
            topic=f"stations/{topic[1]}/locker/{topic[3]}/confirm",
            payload=payload,
            qos=2)
        print(f"Confirmed state {payload.upper()} for locker {
              topic[3]} at station {topic[1]}.")
        await asyncio.sleep(0.1)  # Non-blocking delay

    elif is_action_report(msg.topic):
        await asyncio.sleep(0.1)  # Non-blocking delay
        mqttc.publish(
            topic=f"stations/{topic[1]}/terminal/confirm",
            payload="IDLE",
            qos=2)


# Set up MQTT client
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = lambda client, userdata, msg: asyncio.run(
    on_message(client, userdata, msg))
mqttc.connect("localhost", 1883, 60)

mqttc.subscribe('stations/#')

os.system('clear')

# Run MQTT loop in a separate thread
mqttc.loop_forever()
