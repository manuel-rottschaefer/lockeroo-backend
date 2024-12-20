import paho.mqtt.client as mqtt
from time import sleep
import os


def on_connect(_client, _userdata, _flags, _reason_code, _properties):
    '''The callback for when the client receives a CONNACK response from the server.'''
    # Station subscriptions
    mqttc.subscribe('stations/#')


def on_subscribe(_client, _userdata, _mid, reason_code_list, _properties):
    '''Callback for subscription feedback'''
    pass


def on_message(_client, _userdata, msg: mqtt.MQTTMessage):
    '''The callback for when a PUBLISH message is received from the server.'''
    topic = msg.topic.split('/')[2:]
    payload = msg.payload.decode('utf-8')

    if topic == ['terminal', 'instruct'] and payload in ['VERIFICATION', 'PAYMENT', 'IDLE']:
        mqttc.publish(
            topic=f"stations/{msg.topic.split('/')[1]}/terminal/confirm",
            payload=payload,
            qos=2)


# Set up MQTT client
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.on_subscribe = on_subscribe
mqttc.connect("localhost", 1883, 60)

mqttc.subscribe('stations/#')

os.system('clear')

# Run MQTT loop in a separate thread
mqttc.loop_forever()
