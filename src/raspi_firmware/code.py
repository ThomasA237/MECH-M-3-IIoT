# code.py – Raspberry Pi Pico W / DHT11 / MQTT / HTTP
# CircuitPython – Group 6
# Verwendet lib/toml.py und das bestehende CircuitPython-Bundle.

import time
import board
import digitalio
import wifi
import socketpool
import adafruit_dht
import adafruit_ntp
import rtc
import json
import toml
import adafruit_minimqtt.adafruit_minimqtt as MQTT


# ==========================================
# 1. Konfiguration
# ==========================================

class ConfigManager:
    """Laedt die settings.toml und verwaltet Aenderungen im RAM."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.settings = {}

    def load_settings(self):
        with open(self.filepath, "r") as file:
            self.settings = toml.load(file)
        self.settings["reading_interval_seconds"] = max(
            2, int(self.settings["reading_interval_seconds"])
        )
        return self.settings

    def save_settings(self, settings):
        """Optional: dauerhaft speichern (nur bei beschreibbarem CIRCUITPY).

        Achtung: Standardmaessig ist CIRCUITPY aus dem Programm heraus
        schreibgeschuetzt. Die TOML-Kommentare gehen beim Speichern verloren.
        Diese Methode wird von POST /config bewusst NICHT aufgerufen.
        """
        try:
            with open(self.filepath, "w") as file:
                toml.dump(settings, file)
            return True
        except OSError as error:
            print("Konfiguration konnte nicht gespeichert werden:", error)
            return False

    @property
    def reading_interval(self):
        return self.settings["reading_interval_seconds"]

    def set_reading_interval(self, value):
        if type(value) is not int or value < 2:
            raise ValueError("reading_interval_seconds muss >= 2 sein")
        self.settings["reading_interval_seconds"] = value


# ==========================================
# 2. WLAN
# ==========================================

class NetworkManager:
    """Verwaltet die WLAN-Verbindung und den Socket-Pool."""

    def __init__(self, ssid, password):
        self.ssid = ssid
        self.password = password
        self.pool = None

    def connect(self):
        for attempt in range(1, 4):
            try:
                if not wifi.radio.connected:
                    print("Verbinde mit WLAN (Versuch {})...".format(attempt))
                    wifi.radio.connect(self.ssid, self.password)
                if self.is_connected():
                    print("WLAN verbunden. IP:", self.get_ip())
                    if self.pool is None:
                        self.pool = socketpool.SocketPool(wifi.radio)
                    return True
            except (OSError, RuntimeError, ValueError) as error:
                print("WLAN-Fehler:", error)
            if attempt < 3:
                time.sleep(2)
        return False

    def is_connected(self):
        return bool(wifi.radio.connected)

    def get_ip(self):
        return str(wifi.radio.ipv4_address)


# ==========================================
# 3. Sensor
# ==========================================

class Sensor:
    """Liest Temperatur und Luftfeuchtigkeit vom DHT11."""

    def __init__(self, pin_number):
        pin = getattr(board, "GP" + str(pin_number))
        self.dht = adafruit_dht.DHT11(pin)

    def read_data(self):
        try:
            temperature = self.dht.temperature
            humidity = self.dht.humidity
            if temperature is None or humidity is None:
                return None
            return {"temperature": temperature, "humidity": humidity}
        except (RuntimeError, OSError) as error:
            print("DHT11-Messfehler:", error)
            return None


# ==========================================
# 4. MQTT
# ==========================================

class MqttClient:
    """Kapselt MiniMQTT, Telemetrie und Last Will."""

    def __init__(self, config, pool):
        self.topic = config["telemetry_topic"]
        self.status_topic = config["status_topic"]
        self.connected = False
        self.client = MQTT.MQTT(
            broker=config["broker_address"],
            port=config["broker_port"],
            username=config["mqtt_username"],
            password=config["mqtt_password"],
            client_id=config["device_id"],
            socket_pool=pool,
            keep_alive=30,
        )
        self.client.will_set(
            self.status_topic, "offline", qos=1, retain=True
        )

    def connect(self):
        self.client.connect()
        self.connected = True
        self.publish_status("ok")
        print("MQTT verbunden. Status: ok")

    def reconnect(self):
        self.client.reconnect()
        self.connected = True
        self.publish_status("ok")
        print("MQTT wieder verbunden. Status: ok")

    def is_connected(self):
        try:
            return self.connected and self.client.is_connected()
        except (OSError, RuntimeError, MQTT.MMQTTException):
            return False

    def publish_telemetry(self, data):
        payload = {
            "timestamp": get_timestamp(),
            "value": data["temperature"],
            "unit": "°C",
        }
        try:
            self.client.publish(self.topic, json.dumps(payload))
        except (OSError, RuntimeError, MQTT.MMQTTException):
            self.connected = False
            raise
        print("MQTT gesendet:", json.dumps(payload))
        return payload

    def publish_status(self, status):
        self.client.publish(self.status_topic, status, qos=1, retain=True)

    def loop(self):
        try:
            self.client.loop(timeout=1.1)
        except (OSError, RuntimeError, MQTT.MMQTTException):
            self.connected = False
            raise


# ==========================================
# 5. HTTP-Server
# ==========================================

class WebServer:
    """Nicht blockierende HTTP-API mit socketpool."""

    MAX_REQUEST_BYTES = 4096
    MAX_BODY_BYTES = 1024
    REQUEST_TIMEOUT_SECONDS = 8

    def __init__(self, config_manager, network_manager, mqtt_client, start_time):
        self.config_manager = config_manager
        self.network_manager = network_manager
        self.mqtt_client = mqtt_client
        self.start_time = start_time
        self.pool = network_manager.pool

        self.server = None
        self.client = None
        self.request = bytearray()
        self.response = b""
        self.sent = 0
        self.client_since = 0
        self.next_start_attempt = 0
        self.buffer = bytearray(512)

        self.last_telemetry = None
        self.last_humidity = None

    def start(self):
        try:
            self.server = self.pool.socket(self.pool.AF_INET, self.pool.SOCK_STREAM)
            try:
                self.server.setsockopt(
                    self.pool.SOL_SOCKET, self.pool.SO_REUSEADDR, 1
                )
            except (OSError, AttributeError):
                pass  # Nicht auf jeder Firmware-Version wirksam
            self.server.bind(("0.0.0.0", 80))
            self.server.listen(1)
            self.server.setblocking(False)
            print("HTTP-Server gestartet: http://{}/".format(
                self.network_manager.get_ip()
            ))
            return True
        except OSError as error:
            print("HTTP-Port noch nicht bereit:", error)
            if self.server is not None:
                self.server.close()
            self.server = None
            self.next_start_attempt = time.monotonic() + 5
            return False

    def _close_client(self):
        if self.client is not None:
            try:
                self.client.close()
            except OSError:
                pass
        self.client = None
        self.request = bytearray()
        self.response = b""
        self.sent = 0

    def _queue_response(self, status, data, content_type="application/json", allow=""):
        if isinstance(data, dict):
            body = json.dumps(data).encode("utf-8")
        elif isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = data
        extra = "Allow: {}\r\n".format(allow) if allow else ""
        headers = (
            "HTTP/1.1 {}\r\n"
            "Content-Type: {}\r\n"
            "Content-Length: {}\r\n"
            "Connection: close\r\n"
            "{}"
            "\r\n"
        ).format(status, content_type, len(body), extra)
        self.response = headers.encode("utf-8") + body
        self.sent = 0

    def _handle_get_request(self, path):
        if path == b"/":
            self._queue_response("200 OK", "Hallo vom Pico W!", "text/plain")
        elif path == b"/config":
            self._queue_response("200 OK", {
                "reading_interval_seconds": self.config_manager.reading_interval
            })
        elif path == b"/status":
            self._queue_response("200 OK", {
                "device_id": self.config_manager.settings["device_id"],
                "uptime_seconds": int(time.monotonic() - self.start_time),
                "wifi_connected": self.network_manager.is_connected(),
                "mqtt_connected": self.mqtt_client.is_connected(),
                "last_telemetry": self.last_telemetry,
                "last_humidity_percent": self.last_humidity,
            })
        else:
            self._queue_response("404 Not Found", "Not Found", "text/plain")

    def _handle_post_request(self, body):
        try:
            new_config = json.loads(body.decode("utf-8"))
            if not isinstance(new_config, dict) or (
                set(new_config) != {"reading_interval_seconds"}
            ):
                raise ValueError("Unbekannte oder fehlende Felder")
            new_interval = new_config["reading_interval_seconds"]
            self.config_manager.set_reading_interval(new_interval)
            print("Neues Messintervall:", new_interval, "Sekunden (nur RAM)")
            self._queue_response("200 OK", {
                "reading_interval_seconds": new_interval
            })
        except (ValueError, TypeError, UnicodeError) as error:
            print("Ungueltige Konfiguration:", error)
            self._queue_response("400 Bad Request", {
                "error": "Invalid configuration"
            })

    def _process_request(self):
        delimiter = b"\r\n\r\n"
        if delimiter not in self.request:
            return

        headers, body = bytes(self.request).split(delimiter, 1)
        lines = headers.split(b"\r\n")
        parts = lines[0].split(b" ")
        if len(parts) != 3 or not parts[2].startswith(b"HTTP/1."):
            self._queue_response("400 Bad Request", {"error": "Bad request line"})
            return

        method, path = parts[0], parts[1].split(b"?", 1)[0]
        print("HTTP-Anfrage:", method, path)

        
        # Content-Length für alle HTTP-Methoden prüfen
        # (auch für TRACE, PUT usw.)

        declared_length = None

        for line in lines[1:]:
            if line.lower().startswith(b"content-length:"):
                try:
                    declared_length = int(
                        line.split(b":", 1)[1].strip()
                    )
                except ValueError:
                    self._queue_response(
                        "400 Bad Request",
                        {"error": "Invalid Content-Length"}
                    )
                    return
                break

        # Ungültige oder zu große Bodies ablehnen
        if declared_length is not None:
            if declared_length < 0 or declared_length > self.MAX_BODY_BYTES:
                self._queue_response(
                    "400 Bad Request",
                    {"error": "Invalid Content-Length"}
                )
                return

            # Warten, bis der komplette Body empfangen wurde
            if len(body) < declared_length:
                return


        if path not in (b"/", b"/config", b"/status"):
            self._queue_response("404 Not Found", "Not Found", "text/plain")
            return

        allowed = "GET, POST" if path == b"/config" else "GET"
        if method not in ((b"GET", b"POST") if path == b"/config" else (b"GET",)):
            self._queue_response(
                "405 Method Not Allowed", "Method Not Allowed",
                "text/plain", allow=allowed
            )
            return

        if method == b"GET":
            self._handle_get_request(path)
            return

        # POST /config: Header und Body koennen in getrennten TCP-Paketen kommen.
        content_length = None
        content_type = None
        for line in lines[1:]:
            if b":" not in line:
                continue
            key, value = line.split(b":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == b"content-length":
                try:
                    content_length = int(value)
                except ValueError:
                    content_length = -1
            elif key == b"content-type":
                content_type = value.lower().split(b";", 1)[0].strip()
            elif key == b"transfer-encoding":
                self._queue_response("400 Bad Request", {
                    "error": "Chunked transfer not supported"
                })
                return

        if (content_length is None or content_length < 0
                or content_length > self.MAX_BODY_BYTES):
            self._queue_response("400 Bad Request", {
                "error": "Invalid Content-Length"
            })
            return
        if content_type != b"application/json":
            self._queue_response("400 Bad Request", {
                "error": "Expected application/json"
            })
            return
        if len(body) < content_length:
            return  # Noch nicht alle Bytes angekommen
        self._handle_post_request(body[:content_length])

    def reset(self):
        """Sockets nach einem WLAN-Verbindungsabbruch neu initialisieren."""
        self._close_client()
        if self.server is not None:
            try:
                self.server.close()
            except OSError:
                pass
        self.server = None
        self.next_start_attempt = time.monotonic() + 1

    def poll(self):
        # Ohne WLAN lassen sich HTTP-Verbindungen nicht bedienen.
        if not self.network_manager.is_connected():
            return

        # Der Webserver wird nach EADDRINUSE spaeter erneut gestartet.
        if self.server is None:
            if time.monotonic() >= self.next_start_attempt:
                self.start()
            return

        if self.client is None:
            try:
                self.client, address = self.server.accept()
                self.client.setblocking(False)
                self.request = bytearray()
                self.response = b""
                self.sent = 0
                self.client_since = time.monotonic()
            except OSError:
                return  # Keine neue Verbindung

        if time.monotonic() - self.client_since > self.REQUEST_TIMEOUT_SECONDS:
            print("HTTP TIMEOUT – Verbindung wird geschlossen")
            self._close_client()
            return

        # Antworten stueckweise senden, auch bei nicht blockierendem Socket.
        if self.response:
            try:
                count = self.client.send(self.response[self.sent:])
                if count:
                    self.sent += count
                if self.sent >= len(self.response):
                    self._close_client()
            except OSError:
                pass  # Spaeter erneut versuchen oder nach Timeout schliessen
            return

        try:
            count = self.client.recv_into(self.buffer)
            if count == 0:
                self._close_client()
                return
            if count > 0:
                self.request.extend(self.buffer[:count])
        except OSError:
            return  # Noch keine Daten vorhanden

        if len(self.request) > self.MAX_REQUEST_BYTES:
            self._queue_response("400 Bad Request", {
                "error": "Request too large"
            })
            return

        self._process_request()


# ==========================================
# 6. Hauptprogramm
# ==========================================

def get_timestamp():
    """Aktuelle RTC-Zeit als UTC im ISO-8601-Format."""
    now = time.localtime()
    return (
        "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(
            now.tm_year, now.tm_mon, now.tm_mday,
            now.tm_hour, now.tm_min, now.tm_sec
        )
    )


def main():
    start_time = time.monotonic()
    led = digitalio.DigitalInOut(board.LED)
    led.direction = digitalio.Direction.OUTPUT
    led.value = False

    config_manager = ConfigManager("/settings.toml")
    config = config_manager.load_settings()
    print("Konfiguration geladen.")

    network = NetworkManager(config["wifi_ssid"], config["wifi_password"])
    if not network.connect():
        raise RuntimeError("WLAN-Verbindung fehlgeschlagen")

    ntp = adafruit_ntp.NTP(network.pool, tz_offset=0)
    rtc.RTC().datetime = ntp.datetime
    print("Uhrzeit synchronisiert:", get_timestamp())

    sensor = Sensor(config["sensor_pin"])
    mqtt = MqttClient(config, network.pool)
    mqtt.connect()
    led.value = True

    web = WebServer(config_manager, network, mqtt, start_time)
    web.start()

    last_read = time.monotonic() - config_manager.reading_interval
    next_mqtt_retry = 0
    next_wifi_retry = 0

    while True:
        # WLAN nur bei Verbindungsverlust erneut aufbauen.
        # Der Wiederverbindungsversuch kann kurz blockieren.
        if not network.is_connected() and time.monotonic() >= next_wifi_retry:
            next_wifi_retry = time.monotonic() + 10
            mqtt.connected = False
            if network.connect():
                web.reset()
                next_mqtt_retry = 0

        web.poll()

        # Kurzes MQTT-Timeout, damit HTTP-Anfragen weiter bearbeitet werden.
        if mqtt.connected:
            try:
                mqtt.loop()
            except (OSError, RuntimeError, MQTT.MMQTTException) as error:
                print("MQTT-Fehler:", error)
                mqtt.connected = False
                led.value = False
                next_mqtt_retry = time.monotonic() + 5

        if not mqtt.is_connected() and time.monotonic() >= next_mqtt_retry:
            next_mqtt_retry = time.monotonic() + 5
            try:
                if network.is_connected():
                    mqtt.reconnect()
                    led.value = True
            except (OSError, RuntimeError, MQTT.MMQTTException) as error:
                mqtt.connected = False
                print("MQTT-Wiederverbindung fehlgeschlagen:", error)

        if time.monotonic() - last_read >= config_manager.reading_interval:
            last_read = time.monotonic()
            data = sensor.read_data()
            if data is None:
                led.value = False
                if mqtt.is_connected():
                    try:
                        mqtt.publish_status("error")
                    except (OSError, RuntimeError, MQTT.MMQTTException):
                        mqtt.connected = False
                continue

            web.last_humidity = data["humidity"]
            print("Temperatur:", data["temperature"], "°C")
            print("Luftfeuchtigkeit:", data["humidity"], "%")
            if mqtt.is_connected():
                try:
                    payload = mqtt.publish_telemetry(data)
                    web.last_telemetry = payload
                    mqtt.publish_status("ok")
                    led.value = True
                except (OSError, RuntimeError, MQTT.MMQTTException) as error:
                    print("MQTT-Sendefehler:", error)
                    mqtt.connected = False
                    led.value = False

        time.sleep(0.05)


main()
