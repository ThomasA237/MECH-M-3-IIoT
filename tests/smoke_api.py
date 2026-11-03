"""Reproduzierbare HTTP-Smoke-Tests fuer den Pico W (nur Python-Standardbibliothek).

Aufruf aus dem Repository-Hauptverzeichnis:
    python tests/smoke_api.py --url http://192.168.0.79

WARNUNG: POST /config veraendert das Intervall waehrend des Tests kurzzeitig
im RAM. Der Ausgangswert wird im finally-Block wiederhergestellt.
"""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(base_url, method, path, json_body=None, raw_body=None):
    if json_body is not None and raw_body is not None:
        raise ValueError("json_body und raw_body duerfen nicht zusammen verwendet werden")
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
    elif raw_body is not None:
        data = raw_body.encode("utf-8")
    else:
        data = None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=15) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, dict(error.headers), error.read().decode("utf-8")


def check(label, condition, explanation=""):
    if not condition:
        raise AssertionError("{}: {}".format(label, explanation or "unerwartete Antwort"))
    print("[OK] " + label)


def json_object(body):
    obj = json.loads(body)
    check("Antwort ist JSON-Objekt", isinstance(obj, dict))
    return obj


def run(base_url):
    # 1. GET / mit einfachem Text.
    code, _, body = request(base_url, "GET", "/")
    check("GET / -> 200 mit Text", code == 200 and len(body) > 0)

    # 2. Ausgangswert merken (fuer spaeteres Wiederherstellen).
    code, _, body = request(base_url, "GET", "/config")
    check("GET /config -> 200", code == 200)
    config = json_object(body)
    original = config.get("reading_interval_seconds")
    check("Intervall ist Ganzzahl >= 2", type(original) is int and original >= 2)

    # 3. Statusformat und moegliche Null-Werte pruefen.
    code, _, body = request(base_url, "GET", "/status")
    check("GET /status -> 200", code == 200)
    status = json_object(body)
    expected = {
        "device_id", "uptime_seconds", "wifi_connected", "mqtt_connected",
        "last_telemetry", "last_humidity_percent",
    }
    check("Statusfelder vorhanden", expected.issubset(status))
    check("device_id ist String", isinstance(status["device_id"], str))
    check("Uptime ist nichtnegative Ganzzahl", type(status["uptime_seconds"]) is int
          and status["uptime_seconds"] >= 0)
    check("WLAN/MQTT-Status sind Boolean", type(status["wifi_connected"]) is bool
          and type(status["mqtt_connected"]) is bool)
    humidity = status["last_humidity_percent"]
    check("Luftfeuchtigkeit ist Zahl oder null", humidity is None
          or (type(humidity) in (int, float)))
    telemetry = status["last_telemetry"]
    check("Telemetrie ist Objekt oder null", telemetry is None
          or (isinstance(telemetry, dict)
              and {"timestamp", "value", "unit"}.issubset(telemetry)))

    # 4. Fehlerfaelle und Robustheit.
    code, _, _ = request(base_url, "GET", "/does-not-exist")
    check("Unbekannter Pfad -> 404", code == 404)

    code, headers, _ = request(base_url, "DELETE", "/config")
    allow = headers.get("Allow", headers.get("allow", ""))
    check("Unzulaessige Methode -> 405 und Allow", code == 405
          and "GET" in allow and "POST" in allow)

    code, _, _ = request(base_url, "POST", "/config", raw_body="{invalid json")
    check("Kaputtes JSON -> 400", code == 400)

    code, _, _ = request(base_url, "POST", "/config", json_body={
        "reading_interval_seconds": 10, "device_id": "should-not-change"
    })
    check("device_id nicht schreibbar -> 400", code == 400)

    code, _, _ = request(base_url, "POST", "/config", json_body={
        "reading_interval_seconds": 1
    })
    check("Intervall unter 2 -> 400", code == 400)

    # 5. Gueltige Konfigurationsaenderung + GET-Pruefung, danach Restore.
    try:
        code, _, body = request(base_url, "POST", "/config", json_body={
            "reading_interval_seconds": 10
        })
        check("POST /config gueltig -> 200", code == 200)
        check("POST-Antwort enthaelt neuen Wert",
              json_object(body).get("reading_interval_seconds") == 10)

        code, _, body = request(base_url, "GET", "/config")
        check("GET /config liefert geaenderten Wert", code == 200
              and json_object(body).get("reading_interval_seconds") == 10)
    finally:
        code, _, body = request(base_url, "POST", "/config", json_body={
            "reading_interval_seconds": original
        })
        check("Urspruengliches Intervall wiederhergestellt", code == 200)

    code, _, _ = request(base_url, "GET", "/status")
    check("Server laeuft nach Fehlerfaellen weiter", code == 200)
    print("\nALLE SMOKE-TESTS BESTANDEN")


def main():
    parser = argparse.ArgumentParser(description="Pico W HTTP-Smoke-Tests")
    parser.add_argument("--url", required=True, help="z.B. http://192.168.0.79")
    args = parser.parse_args()
    try:
        run(args.url)
    except (AssertionError, URLError, TimeoutError, OSError, ValueError) as error:
        print("\nTEST FEHLGESCHLAGEN: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
