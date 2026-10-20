import time
import board
import adafruit_dht

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