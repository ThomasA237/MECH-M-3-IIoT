
# ==========================================
# 1. Bibliotheken importieren
# ==========================================

import time
import board
import adafruit_dht
import wifi
import socketpool
import toml
import json
import rtc
import adafruit_ntp
import adafruit_minimqtt.adafruit_minimqtt as MQTT


# ==========================================
# 2. Konfiguration laden
# ==========================================

with open("/settings.toml", "r") as file:
    settings = toml.load(file)

ssid = settings["wifi_ssid"]
password = settings["wifi_password"]

topic = settings["telemetry_topic"]
status_topic = settings["status_topic"]

reading_interval = max(2, settings["reading_interval_seconds"])


# ==========================================
# 3. WLAN-Verbindung herstellen
# ==========================================

print("Verbinde mit WLAN...")

wifi.radio.connect(ssid, password)

print("WLAN verbunden.")
print("IP-Adresse:", wifi.radio.ipv4_address)

pool = socketpool.SocketPool(wifi.radio)


# ==========================================
# 4. Uhrzeit über NTP synchronisieren
# ==========================================

ntp = adafruit_ntp.NTP(pool, tz_offset=0)
rtc.RTC().datetime = ntp.datetime

print("Uhrzeit erfolgreich synchronisiert.")


# Funktion zur Erstellung eines UTC-Zeitstempels
def get_timestamp():
    now = time.localtime()

    return (
        f"{now.tm_year:04d}-"
        f"{now.tm_mon:02d}-"
        f"{now.tm_mday:02d}T"
        f"{now.tm_hour:02d}:"
        f"{now.tm_min:02d}:"
        f"{now.tm_sec:02d}Z"
    )


# ==========================================
# 5. DHT11-Sensor initialisieren
# ==========================================

sensor_pin = getattr(board, "GP" + str(settings["sensor_pin"]))
dht = adafruit_dht.DHT11(sensor_pin)


# ==========================================
# 6. MQTT-Client initialisieren
# ==========================================

mqtt_client = MQTT.MQTT(
    broker=settings["broker_address"],
    port=settings["broker_port"],
    username=settings["mqtt_username"],
    password=settings["mqtt_password"],
    client_id="Group_6_Pico",
    socket_pool=pool,
    # Keep-Alive-Intervall in Sekunden (Bedeutet, dass der Client alle 30 Sekunden eine Nachricht an den Broker sendet, um die Verbindung aufrechtzuerhalten)
    keep_alive=30
)


# ==========================================
# 7. Last Will konfigurieren
# ==========================================

# Bei unerwartetem Verbindungsabbruch
# veröffentlicht der Broker "offline".

mqtt_client.will_set(
    status_topic,
    "offline",
    # QoS 1: Nachricht wird mindestens einmal zugestellt
    qos=1,
    retain=True
)


# ==========================================
# 8. MQTT-Verbindung herstellen
# ==========================================

print("Verbinde mit MQTT-Broker...")

mqtt_client.connect()

print("MQTT verbunden.")


# Online-Status veröffentlichen
mqtt_client.publish(
    status_topic,
    "ok",
    qos=1,
    retain=True
)

print("Status gesendet: ok")


# ==========================================
# 9. Hauptschleife
# ==========================================

last_read = time.monotonic() - reading_interval

while True:

    # MQTT-Verbindung aufrechterhalten
    try:
        mqtt_client.loop(timeout=1.1)

    except (OSError, RuntimeError, MQTT.MMQTTException) as error:
        print("MQTT-Fehler:", error)

        try:
            mqtt_client.reconnect()
            mqtt_client.publish(
                status_topic,
                "ok",
                qos=1,
                retain=True
            )
            print("MQTT wieder verbunden.")

        except (OSError, RuntimeError, MQTT.MMQTTException) as error:
            print("Wiederverbindung fehlgeschlagen:", error)
            time.sleep(2)

        continue

    # Messintervall überprüfen
    if time.monotonic() - last_read >= reading_interval:

        last_read = time.monotonic()

        try:
            temperatur = dht.temperature
            luftfeuchtigkeit = dht.humidity

            print("Temperatur:", temperatur, "°C")
            print("Luftfeuchtigkeit:", luftfeuchtigkeit, "%")

            # Nur gültige Messwerte senden
            if temperatur is not None:

                # JSON-Payload mit echten Messwerten
                payload = {
                    "timestamp": get_timestamp(),
                    "value": temperatur,
                    "unit": "°C"
                }

                payload_json = json.dumps(payload)

                # MQTT-Nachricht veröffentlichen
                mqtt_client.publish(topic, payload_json)

                print("MQTT gesendet:", payload_json)
                print("--------------------")

        except RuntimeError as error:
            print("Messfehler:", error)

        except (OSError, MQTT.MMQTTException) as error:
            print("MQTT-Sendefehler:", error)

    time.sleep(0.05)
