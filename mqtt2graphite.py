#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import socket
import json
import time
import datetime
import logging
import traceback
import sys
import argparse
import requests
from requests.auth import HTTPBasicAuth

appName = 'mqtt2graphite'

try:
    from systemd.journal import JournalHandler
    logger = logging.getLogger(appName)
    logger.addHandler(JournalHandler(SYSLOG_IDENTIFIER=appName))
except ImportError:
    logger = logging.getLogger(appName)
    stdout = logging.StreamHandler(sys.stdout)
    logger.addHandler(stdout)
finally:
    logger.setLevel(logging.DEBUG)

global Sensors, LastTimeSent, args, Prefix
Prefix = "zigbee2mqtt"
Sensors = ["living-room-sensor1", "garage-socket1", "kitchen-socket1", "metoffice", "noweather", "netatmo", "openweathermap", "KeepAlive"]
LastTimeSent = {}
token = ""

def netcat(host, port, content):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, int(port)))
    s.sendall(content.encode())
    s.shutdown(socket.SHUT_WR)
    time.sleep(1)
    s.close()

def graphiteHttpPost(token, metric, sensor):
    url = "https://graphite.debroglie.net/graphiteSink.php"
    resp = requests.post(
        url,
        data=metric.encode())
    if resp.status_code == 202:
        logger.debug("%s: sent %s to graphite"%(sensor, metric))
    else:
        logger.error("%s: failed to send %s to graphite"%(sensor, metric))
        resp.raise_for_status()

def on_connect(client, userdata, flags, rc):
  logger.debug("Connected with result code "+str(rc))
  client.subscribe([("zigbee2mqtt/#",0), ("homeassistant/#",0), ("openweathermap/#",0), ("KeepAlive/#", 0)])

def on_message(client, userdata, msg):
    global LastTimeSent
    logger.debug(msg.payload.decode())
    for sensor in Sensors:
        if sensor in msg.topic:
            if sensor in LastTimeSent:
                if (datetime.datetime.now() - LastTimeSent[sensor]).total_seconds() < 60:
                    logger.debug("%s: Skipping, less then 60sec"%sensor)
                    break
            LastTimeSent[sensor] = datetime.datetime.now()
            try:
                payload = json.loads(msg.payload.decode())
            except:
                logger.error("Cannot parse json \"%s\""%msg.payload.decode())
                continue
            for type, value in payload.items():
                if isinstance(value, str):
                    if value == "ON":
                        metric = "%s.%s.%s.%s %d"%(args.graphiteKey, Prefix, sensor, type, 1)
                    elif value == "OFF":
                        metric = "%s.%s.%s.%s %d"%(args.graphiteKey, Prefix, sensor, type, 0)
                    else:
                        metric = "%s.%s.%s.%s %s"%(args.graphiteKey, Prefix, sensor, type, value)
                else:
                    try:
                        metric = "%s.%s.%s.%s %f"%(args.graphiteKey, Prefix, sensor, type, value)
                    except TypeError:
                        logger.error("Invalid type: " + "%s.%s.%s.%s %s"%(args.graphiteKey, Prefix, sensor, type, value))
                        metric = None

                if metric is not None:
                    netcat(args.graphiteHost, args.graphitePort, metric)
                    logger.debug("%s: sent %s to graphite"%(sensor, metric))

def on_message_http(client, userdata, msg):
    global LastTimeSent, token
    logger.debug(msg.payload.decode())
    logger.debug(Sensors)
    logger.debug(msg.topic)
    for sensor in Sensors:
        if sensor in msg.topic:
            try:
                payload = json.loads(msg.payload.decode())
            except:
                logger.error("Cannot parse json \"%s\""%msg.payload.decode())
                continue
            for type, value in payload.items():
                if isinstance(value, str):
                    if value == "ON":
                        metric = "%s.%s.%s.%s %d"%(token, Prefix, sensor, type, 1)
                    elif value == "OFF":
                        metric = "%s.%s.%s.%s %d"%(token, Prefix, sensor, type, 0)
                    else:
                        metric = "%s.%s.%s.%s %s"%(token, Prefix, sensor, type, value)
                else:
                    try:
                        metric = "%s.%s.%s.%s %f"%(token, Prefix, sensor, type, value)
                    except TypeError:
                        logger.error("Invalid type: " + "%s.%s.%s.%s %s"%(token, Prefix, sensor, type, value))
                        metric = None

                if metric is not None:
                    graphiteHttpPost(args.graphiteKey, metric, sensor)

def main():
    global args, token
    parser = argparse.ArgumentParser(description='subscribe to topics and send data to graphite')
    parser.add_argument('--graphiteKey', metavar='GRAPHITEKEY', required=True,
                        help='graphite key')
    parser.add_argument('--graphiteHost', metavar='GRAPHITEHOST', default="graphite.gra1.metrics.ovh.net",
                        help='graphite host')
    parser.add_argument('--graphitePort', metavar='GRAPHITEPORT', default=2003,
                        help='graphite port', type=int)
    parser.add_argument('--mqttHost', metavar='MQTTHOST', default="localhost",
                        help='mqtt host')
    parser.add_argument('--mqttPort', metavar='MQTTPORT', default=1883,
                        help='mqtt port', type=int)
    args = parser.parse_args()

    token = args.graphiteKey

    client = mqtt.Client()
    client.connect(args.mqttHost,args.mqttPort,60)

    client.on_connect = on_connect
    client.on_message = on_message_http

    client.loop_forever()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error('An unexpected error occurred')
        logger.error("".join(traceback.format_exception(None,e, e.__traceback__)).replace("\n",""))
        sys.exit(2)
