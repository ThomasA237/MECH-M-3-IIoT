# Automatisierte HTTP-API-Tests (Raspberry Pi Pico W)

## Ziel und Testumfang

Der Pico bietet unverschluesseltes HTTP auf Port 80 im lokalen WLAN:
`GET /`, `GET /config`, `POST /config` und `GET /status`.

- `smoke_api.py`: reproduziert die im Aufgabenblatt geforderten curl-Testfaelle
  (200, JSON, POST/GET-Konfigurationsuebernahme, 400/404/405, `/status`).
- `run_api_tests.ps1`: startet die Smoke-Tests und die OpenAPI-basierten
  **Schemathesis**-Phasen Examples und Coverage (ein Worker, sequentiell).
- `docs/iot-specs/openapi.yaml`: Vertrag der HTTP-API; `GET /status` ist enthalten.

## Voraussetzungen

1. Laptop und Pico W im selben erreichbaren WLAN; WLAN-Client-Isolation darf
   HTTP auf TCP-Port 80 nicht verhindern. IP vom Pico-Serial-Monitor ablesen.
2. Pico mit `code.py` und `settings.toml` gestartet; `HTTP-Server gestartet:`
   in der seriellen Konsole sichtbar.
3. Python und Schemathesis installiert (getestet mit Schemathesis 4.33.0):

   ```powershell
   python -m pip install schemathesis==4.33.0
   ```

## Schnelltest

Aus dem **Repository-Hauptverzeichnis**:

```powershell
curl.exe -v http://192.168.0.79/status
python .\tests\smoke_api.py --url http://192.168.0.79
```

Oder alle Checks in einem Durchlauf (IP anpassen):

```powershell
.\tests\run_api_tests.ps1 -PicoIP 192.168.0.79
```

Nur schneller Smoke-/Examples-Test ohne die laengere Coverage-Phase:

```powershell
.\tests\run_api_tests.ps1 -PicoIP 192.168.0.79 -SkipCoverage
```

Falls die PowerShell-Ausfuehrungsrichtlinie das lokale Skript blockiert, kann
es nach Sichtpruefung mit einem einmaligen Prozessaufruf gestartet werden:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\run_api_tests.ps1 -PicoIP 192.168.0.79
```

## Schemathesis separat ausfuehren

```powershell
schemathesis run .\docs\iot-specs\openapi.yaml --url http://192.168.0.79 --workers 1 --phases examples --request-timeout 10
schemathesis run .\docs\iot-specs\openapi.yaml --url http://192.168.0.79 --workers 1 --phases coverage --request-timeout 10 --max-failures 3
```

Die Coverage-Phase kann auf dem Pico mehrere Minuten dauern. Erst eine
abgeschlossene Ausgabe `No issues found` zaehlt als bestandener Lauf.
Ein manuell abgebrochener Lauf ist **kein** erfolgreicher Coverage-Nachweis.

## Prueffaelle und Sollverhalten

| Testfall | Erwartetes Verhalten |
| --- | --- |
| `GET /` | HTTP 200 mit beliebigem Text |
| `GET /config` | HTTP 200, JSON mit `reading_interval_seconds >= 2` |
| `POST /config` mit `{"reading_interval_seconds":10}` | HTTP 200, anschliessend GET zeigt 10 |
| `GET /status` | HTTP 200, Geraete-/Verbindungsstatus und letzte Werte |
| `GET /does-not-exist` | HTTP 404 |
| `DELETE /config` | HTTP 405, `Allow: GET, POST` |
| `POST /config` mit kaputtem JSON | HTTP 400 |
| `POST /config` mit `device_id` | HTTP 400 |
| `POST /config` mit Intervall 1 | HTTP 400 |
| `GET /status` nach Fehlanfragen | HTTP 200, Server weiter erreichbar |

Der Smoke-Test stellt nach der gueltigen POST-Aenderung das urspruengliche
Intervall wieder her. Die Firmware speichert solche Aenderungen nur im RAM.

## Bereits beobachtete Ergebnisse (03.11.2026; vor `/status`-Ergaenzung)

- Schemathesis Examples: 2/2 Testfaelle bestanden; 1 Operation ohne Beispiel uebersprungen.
- Schemathesis Coverage: 29/29 Testfaelle bestanden; 2/2 Operationen getestet.

Diese frueheren Ergebnisse beziehen sich **nur** auf die damaligen zwei
OpenAPI-Operationen (`GET /config`, `POST /config`). Nach Aufnahme von
`GET /status` sind neue Ergebnisse zu erzeugen. Die neue Fassung ist noch
nicht gegen das reale Geraet verifiziert.

## Einschraenkungen und Sicherheit

Die API nutzt HTTP ohne TLS und derzeit ohne Authentifizierung. Tests daher
nur aus dem freigegebenen lokalen Netz ausfuehren. Die OpenAPI-Spezifikation
muss vor einem Merge mit der gruppenweit vereinbarten API abgeglichen werden.
In das Git-Repository keine echten WLAN-/MQTT-Passwoerter einchecken.
