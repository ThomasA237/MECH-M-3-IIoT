import time
import board
import adafruit_dht

# Steuerung des Wlan-Moduls
import wifi
# Bereitstellung von Socket-Funktionalität
import socketpool
# Import, um auf die Settings zuzugreifen
import os

# Holen der SSID und des Passworts aus den Umgebungsvariablen
ssid = os.getenv("wifi_ssid")
password = os.getenv("wifi_password")

print("Verbinde mit WLAN...")

# Verbinden mit dem WLAN 
wifi.radio.connect(ssid, password)

print("WLAN verbunden.")
print("IP-Adresse:", wifi.radio.ipv4_address)

# Erstellen eines Socket-Pools für die Netzwerkkommunikation
pool = socketpool.SocketPool(wifi.radio)


# Initialisierung des DHT11-Sensors (Sensor ist an Pin GP22 angeschlossen)
dht = adafruit_dht.DHT11(board.GP22)

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
