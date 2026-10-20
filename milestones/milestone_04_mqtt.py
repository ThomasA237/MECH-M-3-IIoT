# Mqtt-Client für die Übertragung von Sensordaten an einen MQTT-Broker
import adafruit_minimqtt.adafruit_minimqtt as MQTT

import time
import board
import adafruit_dht

# Steuerung des Wlan-Moduls
import wifi
# Bereitstellung von Socket-Funktionalität
import socketpool
# Import, um auf die Settings zuzugreifen
import os
import toml

with open("/settings.toml", "r") as file:
    settings = toml.load(file)

# Variablen aus der Konfiguration auslesen
ssid = settings["wifi_ssid"]
password = settings["wifi_password"]

# Zum Senden von Sensordaten im JSON-Format
import json
# Import, um die aktuelle Zeit zu erhalten
import rtc
# Import, um die aktuelle Zeit von einem NTP-Server zu erhalten
import adafruit_ntp

print("Verbinde mit WLAN...")

# Verbinden mit dem WLAN 
wifi.radio.connect(ssid, password)

print("WLAN verbunden.")
print("IP-Adresse:", wifi.radio.ipv4_address)

# Erstellen eines Socket-Pools für die Netzwerkkommunikation
pool = socketpool.SocketPool(wifi.radio)

# Initialisierung des NTP-Clients, um die aktuelle Zeit von einem NTP-Server zu erhalten
ntp = adafruit_ntp.NTP(pool, tz_offset=0)
# Setzen der aktuellen Zeit auf die RTC (Real Time Clock) des Mikrocontrollers
rtc.RTC().datetime = ntp.datetime
# Abrufen der aktuellen Zeit von der RTC
now = time.localtime()
# Timestamp im ISO 8601-Format erstellen
timestamp = (
    f"{now.tm_year:04d}-"
    f"{now.tm_mon:02d}-"
    f"{now.tm_mday:02d}T"
    f"{now.tm_hour:02d}:"
    f"{now.tm_min:02d}:"
    f"{now.tm_sec:02d}Z"
)



# Initialisierung des DHT11-Sensors (Sensor ist an Pin GP22 angeschlossen)
dht = adafruit_dht.DHT11(board.GP22)

# MQTT-Client-ID 
broker = os.getenv("broker_address")
port = os.getenv("broker_port")
username = os.getenv("mqtt_username")
mqtt_password = os.getenv("mqtt_password")
topic = os.getenv("telemetry_topic")


# MQTT-Broker-Einstellungen
mqtt_client = MQTT.MQTT(
    broker=broker,
    port=port,
    username=username,
    password=mqtt_password,
    client_id=client_id,
    socket_pool=pool
)

# eindeutige Client-ID
client_id = "Group_6_Pico"

# Mit Broker verbinden
print("Verbinde mit MQTT-Broker...")
mqtt_client.connect()

print("MQTT verbunden.")

# Testnachricht senden
#message = "Hallo von Group 6 Pico"

#print("Sende:", message)
#mqtt_client.publish(topic, message)

#print("Nachricht gesendet.")

payload = {
    "timestamp": "2026-10-05T13:15:00Z",
    "value": 23.4,
    "unit": "°C"
}

payload_json = json.dumps(payload)

mqtt_client.publish(topic, payload_json)

while True:
    try:
        temperatur = dht.temperature
        luftfeuchtigkeit = dht.humidity

        print("Temperatur:", temperatur, "°C")
        print("Luftfeuchtigkeit:", luftfeuchtigkeit, "%")
        print("--------------------")

    except RuntimeError as error:
        print("Messfehler:", error)

    time.sleep(2)

