import json
import sqlite3
import threading
import time
from flask import Flask, jsonify, render_template
import paho.mqtt.client as mqtt
import serial
import os

app = Flask(__name__)
DB_NAME = "server_room.db"
MQTT_BROKER = "localhost"  # Atau gunakan broker publik seperti test.mosquitto.org
MQTT_PORT = 1883
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = "server/room/sensor"
SERIAL_PORT = (  # Sesuaikan dengan port virtual serial SimulIDE (misal: COM3 atau /dev/ttyUSB0)
    "/tmp/ttyV1"
)
BAUD_RATE = 9600


# Inisialisasi Database SQLite
def init_db():
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute(
      """CREATE TABLE IF NOT EXISTS sensor_logs
               (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                temperature REAL, 
                humidity REAL, 
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)"""
  )
  conn.commit()
  conn.close()


# Callback saat pesan MQTT diterima
def on_message(client, userdata, msg):
  try:
    payload = json.loads(msg.payload.decode())
    temp = payload.get("temperature")
    hum = payload.get("humidity")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(
        "INSERT INTO sensor_logs (temperature, humidity) VALUES (?, ?)",
        (temp, hum),
    )
    conn.commit()
    conn.close()
    print(f"Data disimpan -> Temp: {temp}°C, Hum: {hum}%")
  except Exception as e:
    print("Error parsing MQTT message:", e)


# Thread MQTT Subscriber
def run_mqtt():
  client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

  client.username_pw_set(
      MQTT_USERNAME,
      MQTT_PASSWORD
  )

  client.on_message = on_message

  client.connect(
      MQTT_BROKER,
      MQTT_PORT,
      60
  )

  client.subscribe(MQTT_TOPIC)
  client.loop_start()


# Thread Serial Bridge (Membaca SimulIDE Serial & Publish ke MQTT)
def run_serial_bridge():
  client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

  client.username_pw_set(
      MQTT_USERNAME,
      MQTT_PASSWORD
  )

  client.connect(
      MQTT_BROKER,
      MQTT_PORT,
      60
  )

  try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE)

    while True:
      if ser.in_waiting > 0:
        line = ser.readline().decode("utf-8").strip()

        if line.startswith("{"):
          client.publish(MQTT_TOPIC, line)

      time.sleep(0.1)

  except Exception as e:
    print(
        "Serial Bridge tidak aktif "
        "(pastikan SimulIDE terhubung ke Virtual Port):",
        e,
    )

@app.route("/")
def index():
  return render_template("index.html")


@app.route("/api/data")
def get_data():
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute(
      "SELECT temperature, humidity, timestamp FROM sensor_logs ORDER BY id DESC"
      " LIMIT 20"
  )
  rows = c.fetchall()
  conn.close()

  data = []
  for row in reversed(rows):
    data.append(
        {"temperature": row[0], "humidity": row[1], "timestamp": row[2]}
    )
  return jsonify(data)


if __name__ == "__main__":
  init_db()

  # Jalankan MQTT & Serial Bridge di Background Thread
  threading.Thread(target=run_mqtt, daemon=True).start()
  threading.Thread(target=run_serial_bridge, daemon=True).start()

  app.run(debug=True, port=5000)
