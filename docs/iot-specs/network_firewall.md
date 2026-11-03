# Netzwerk- und Sicherheitsanforderungen fuer den Pico W

## Hinweise fuer die lokale IT-Abteilung

Der Raspberry Pi Pico W verbindet sich als WLAN-Client mit dem lokalen
2,4-GHz-WLAN und baut eine **ausgehende TCP-Verbindung** zum MQTT-Broker
`158.180.44.197:1883` auf. Damit Temperaturmeldungen und Statusnachrichten
ankommen, muss die externe Firewall diesen Zielhost und Zielport freigeben;
Rueckpakete der bestehenden Verbindung muessen zugelassen sein. Die Firmware
synchronisiert beim Start ihre Uhrzeit ueber NTP (**ausgehend UDP 123** zum
konfigurierten/aufgeloesten Zeitserver); falls Hostnamen statt IP-Adressen
genutzt werden, wird ausserdem DNS-Namensaufloesung benoetigt
(typischerweise UDP 53, bei Bedarf TCP 53 zum lokalen Resolver). Eingehend
bietet das Geraet eine unverschluesselte HTTP-API auf **TCP 80** fuer
`GET /config`, `POST /config` und `GET /status`. Dieser Port muss nur fuer
berechtigte Rechner bzw. das lokale Management-Netz erreichbar sein, nicht
aus dem Internet. WLAN-Client-Isolation, getrennte VLANs oder Firewallregeln
zwischen Laptop und Pico koennen den lokalen Zugriff verhindern, auch wenn
beide Geraete WLAN-Zugang und MQTT-Konnektivitaet haben.

| Richtung | Quelle -> Ziel | Transport/Port | Zweck |
| --- | --- | --- | --- |
| Ausgehend | Pico -> `158.180.44.197` | TCP 1883 | MQTT-Publish, Status, Last Will |
| Ausgehend | Pico -> konfigurierter NTP-Server | UDP 123 | UTC-Uhrzeitsynchronisierung beim Start |
| Ausgehend (bei Hostnamen) | Pico -> DNS-Resolver | UDP/TCP 53 | Namensaufloesung |
| Eingehend (nur intern) | Berechtigter Laptop -> Pico-IP | TCP 80 | HTTP-REST-API |

Die exakte NTP-Zieladresse haengt von Bibliothek, DNS und lokalen Einstellungen
ab und muss fuer die tatsaechliche Installation ermittelt werden. MQTT-Topic-
Namen, Geraete-ID und Broker-Zugangsdaten werden aus `settings.toml` geladen;
echte Passwoerter gehoeren nicht ins Repository.

## Fernzugriff und Risiken

Eine **direkte Portweiterleitung von TCP 80 aus dem Internet** auf den Pico
ist nicht zu empfehlen: Die API verwendet derzeit **kein TLS und keine
Authentifizierung**. Unbefugte Personen koennten den Geraetestatus abfragen
oder das Messintervall ueber `POST /config` veraendern; HTTP-Daten koennen
im Netz mitgelesen und veraendert werden. Auch MQTT ueber Port 1883 ist
in der verwendeten Konfiguration nicht TLS-geschuetzt, sodass die IT das
Geraet und seine Brokerverbindungen auf ein geeignetes Segment begrenzen
sollte. Weitere Risiken sind Scans, DoS durch viele HTTP-Anfragen und
dynamische IP-Adressen/NAT bei externem Zugriff.

Fuer Wartung aus der Ferne empfiehlt sich ein **VPN** ins Management-Netz
mit Benutzer-Authentifizierung und Firewall-Regeln, die nur berechtigten
Administratoren Zugriff auf die lokale Pico-IP:80 geben. Alternativ waere
ein abgesicherter Reverse Proxy bzw. Gateway mit HTTPS und Authentifizierung
moeglich; der Pico selbst sollte weiterhin nicht direkt aus dem Internet
erreichbar sein. Fuer produktive Umgebungen waere auch eine TLS-geschuetzte
MQTT-Anbindung (typischerweise Port 8883, falls vom Broker unterstuetzt)
anzustreben. Eine feste DHCP-Reservierung vereinfacht die Erreichbarkeit.

## Grenzen des aktuellen Prototyps

- `POST /config` aktualisiert nur `reading_interval_seconds` im RAM.
  Nach Neustart gilt wieder der Wert aus `settings.toml`.
- Die API verwendet HTTP und hat derzeit keine Zugriffskontrolle.
- MQTT-Keepalive und HTTP-Requests teilen eine Hauptschleife; sehr viele
  Requests koennen die Antwortzeiten eines Microcontrollers vergroessern.
