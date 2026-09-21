import json
import sqlite3
import threading
import time
import os

from flask import Flask, jsonify, render_template
import paho.mqtt.client as mqtt
import serial

app = Flask(__name__)
DB_NAME = "server_room.db"

# MQTT CONFIGURATION
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "server/room/sensor")
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

if not MQTT_USERNAME or not MQTT_PASSWORD:
    raise RuntimeError("MQTT_USERNAME dan MQTT_PASSWORD wajib diatur.")

# SERIAL CONFIGURATION
SERIAL_PORT = os.getenv("SERIAL_PORT", "/tmp/ttyV1")
BAUD_RATE = int(os.getenv("BAUD_RATE", "9600"))

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sensor_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temperature REAL,
            humidity REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        temp = payload.get("temperature")
        hum = payload.get("humidity")

        if temp is None or hum is None:
            print("MQTT payload tidak memiliki temperature/humidity")
            return

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(
            "INSERT INTO sensor_logs (temperature, humidity) VALUES (?, ?)",
            (temp, hum)
        )
        conn.commit()
        conn.close()
        print(f"Data masuk -> Temp: {temp}°C, Hum: {hum}%")

    except Exception as e:
        print("Error parsing MQTT message:", e)

def run_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_message = on_message

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.subscribe(MQTT_TOPIC)
            print(f"MQTT connected: {MQTT_BROKER}:{MQTT_PORT} | Subscribed: {MQTT_TOPIC}")
            client.loop_forever()
        except Exception as e:
            print("MQTT error, retrying in 5 seconds:", e)
            time.sleep(5)

def run_serial_bridge():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_start()  # Memastikan thread pengiriman MQTT berjalan

            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            print(f"Serial connected: {SERIAL_PORT}")

            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if line.startswith("{"):
                        result = client.publish(MQTT_TOPIC, line)
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            print("MQTT publish:", line)
                time.sleep(0.1)

        except Exception as e:
            print("Serial Bridge error, retrying in 5 seconds:", e)
            time.sleep(5)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/data")
def get_data():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT temperature, humidity, timestamp
        FROM sensor_logs
        ORDER BY id DESC
        LIMIT 20
    """)
    rows = c.fetchall()
    conn.close()

    data = [{"temperature": row[0], "humidity": row[1], "timestamp": row[2]} for row in reversed(rows)]
    return jsonify(data)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_mqtt, daemon=True).start()
    threading.Thread(target=run_serial_bridge, daemon=True).start()
    app.run(debug=True, use_reloader=False, port=5000)
