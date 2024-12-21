import paho.mqtt.client as mqtt
import os
import re


def is_terminal_path(topic):
    pattern = r'^stations/[A-Z]{6}/terminal/instruct$'
    return re.match(pattern, topic) is not None


def is_locker_path(topic):
    pattern = r'^stations/[A-Z]{6}/locker/\d{1,2}/instruct$'
    return re.match(pattern, topic) is not None


def on_connect(_client, _userdata, _flags, _reason_code, _properties):
    '''The callback for when the client receives a CONNACK response from the server.'''
    # Station subscriptions
    mqttc.subscribe('stations/#')


def on_message(_client, _userdata, msg: mqtt.MQTTMessage):
    '''The callback for when a PUBLISH message is received from the server.'''
    topic = msg.topic.split('/')
    payload = msg.payload.decode('utf-8')

    if is_terminal_path(msg.topic) and payload in ['VERIFICATION', 'PAYMENT', 'IDLE']:
        print(f"Received mode instruction {
              payload} for station {msg.topic.split('/')[1]}.")
        mqttc.publish(
            topic=f"stations/{msg.topic.split('/')[1]}/terminal/confirm",
            payload=payload,
            qos=2)
        print(f"Confirmed mode {payload} for station {
              msg.topic.split('/')[1]}.")

    elif is_locker_path(msg.topic) and payload in ['locked', 'unlocked']:
        print(f"Received state instruction {payload} for locker {
              topic[3]} at station {topic[1]}.")
        mqttc.publish(
            topic=f"stations/{topic[1]}/locker/{topic[3]}/confirm",
            payload=payload,
            qos=2)
        print(f"Confirmed state {payload} for locker {
              topic[3]} at station {topic[1]}.")


# Set up MQTT client
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.connect("localhost", 1883, 60)

mqttc.subscribe('stations/#')

os.system('clear')

# Run MQTT loop in a separate thread
mqttc.loop_forever()
