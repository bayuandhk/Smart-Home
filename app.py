"""
Smart Home HMI Dashboard - Backend Server
==========================================
Flask + Flask-SocketIO server yang menerima data IoT dari ESP32
melalui HTTP POST dan mem-broadcast ke dashboard via WebSocket.
Juga memiliki mode simulasi untuk testing tanpa hardware.
"""

import random
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

# ──────────────────────────────────────────────
# Inisialisasi Aplikasi
# ──────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'smart-home-pbl-secret-key'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ──────────────────────────────────────────────
# Mode Operasi: True = simulasi, False = data ESP32
# Otomatis berubah ke False saat ESP32 pertama kali kirim data
# ──────────────────────────────────────────────
USE_SIMULATION = True

# ──────────────────────────────────────────────
# Definisi Ruangan & Perangkat
# ──────────────────────────────────────────────
ROOMS = ['ruang_tamu', 'dapur', 'teras', 'kamar']

SENSOR_TYPES = ['fire', 'gas', 'pir']

# State awal semua perangkat
device_state = {
    'lamps': {room: False for room in ROOMS},
    'sensors': {room: {s: 'AMAN' for s in SENSOR_TYPES} for room in ROOMS},
    'gate': 'CLOSED',
    'telemetry': {
        'voltage': 220.0,
        'current': 0.0,
        'power': 0.0,
        'energy': 0.0,
    }
}


def generate_telemetry():
    """Menghasilkan nilai telemetri acak yang realistis."""
    voltage = round(random.uniform(215.0, 225.0), 1)
    current = round(random.uniform(0.5, 5.0), 2)
    power = round(voltage * current, 1)

    # Akumulasi energi (kWh), simulasi kecil tiap interval
    device_state['telemetry']['energy'] += round(power * (3 / 3600), 4)
    energy = round(device_state['telemetry']['energy'], 4)

    return {
        'voltage': voltage,
        'current': current,
        'power': power,
        'energy': energy,
    }


def generate_device_status():
    """Menghasilkan status acak untuk lampu, sensor, dan gate."""
    # Update status lampu (30% chance toggle per ruangan)
    for room in ROOMS:
        if random.random() < 0.30:
            device_state['lamps'][room] = not device_state['lamps'][room]

    # Update status sensor (10% chance menjadi ACTIVE per sensor)
    for room in ROOMS:
        for sensor in SENSOR_TYPES:
            if random.random() < 0.10:
                device_state['sensors'][room][sensor] = 'ACTIVE'
            else:
                device_state['sensors'][room][sensor] = 'AMAN'

    # Update gate (20% chance toggle)
    if random.random() < 0.20:
        device_state['gate'] = 'OPEN' if device_state['gate'] == 'CLOSED' else 'CLOSED'

    return {
        'lamps': dict(device_state['lamps']),
        'sensors': {r: dict(s) for r, s in device_state['sensors'].items()},
        'gate': device_state['gate'],
    }


def background_simulation():
    """Background thread yang mengirim data simulasi setiap 3 detik."""
    print("[SIM] Background simulation thread dimulai...")
    while True:
        socketio.sleep(3)

        # Hentikan simulasi jika ESP32 sudah mengirim data
        if not USE_SIMULATION:
            continue

        telemetry = generate_telemetry()
        devices = generate_device_status()

        payload = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'telemetry': telemetry,
            'lamps': devices['lamps'],
            'sensors': devices['sensors'],
            'gate': devices['gate'],
        }

        socketio.emit('update_status', payload)
        print(f"[SIM] Data terkirim: V={telemetry['voltage']}V | "
              f"P={telemetry['power']}W | Gate={devices['gate']}")


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────
@app.route('/')
def index():
    """Render dashboard utama."""
    return render_template('index.html')


# ──────────────────────────────────────────────
# REST API — Endpoint untuk ESP32
# ──────────────────────────────────────────────
@app.route('/api/esp32', methods=['POST'])
def esp32_data():
    """
    Menerima data JSON dari ESP32 via HTTP POST,
    lalu mem-broadcast ke semua client WebSocket.
    """
    global USE_SIMULATION

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid JSON'}), 400

    # Matikan simulasi saat ESP32 pertama kali kirim data
    if USE_SIMULATION:
        USE_SIMULATION = False
        print("[ESP32] Data asli diterima — simulasi dinonaktifkan")

    # Bangun payload dari data ESP32
    payload = {
        'timestamp': data.get('timestamp', time.strftime('%Y-%m-%d %H:%M:%S')),
        'telemetry': data.get('telemetry', {}),
        'lamps': data.get('lamps', {}),
        'sensors': data.get('sensors', {}),
        'gate': data.get('gate', 'CLOSED'),
    }

    # Update device_state internal
    if payload['telemetry']:
        device_state['telemetry'].update(payload['telemetry'])
    if payload['lamps']:
        device_state['lamps'].update(payload['lamps'])
    if payload['sensors']:
        for room, sensors in payload['sensors'].items():
            if room in device_state['sensors']:
                device_state['sensors'][room].update(sensors)
    device_state['gate'] = payload['gate']

    # Broadcast ke semua client WebSocket
    socketio.emit('update_status', payload)

    print(f"[ESP32] Data diterima: V={payload['telemetry'].get('voltage', '?')}V | "
          f"P={payload['telemetry'].get('power', '?')}W | Gate={payload['gate']}")

    return jsonify({'status': 'ok', 'message': 'Data received and broadcasted'}), 200


# ──────────────────────────────────────────────
# WebSocket Events
# ──────────────────────────────────────────────
@socketio.on('connect')
def handle_connect():
    """Kirim state terakhir saat klien terkoneksi."""
    print("[WS] Client terhubung")

    payload = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'telemetry': dict(device_state['telemetry']),
        'lamps': dict(device_state['lamps']),
        'sensors': {r: dict(s) for r, s in device_state['sensors'].items()},
        'gate': device_state['gate'],
    }
    socketio.emit('update_status', payload)


@socketio.on('disconnect')
def handle_disconnect():
    print("[WS] Client terputus")


# ──────────────────────────────────────────────
# Jalankan Server
# ──────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("  Smart Home HMI Dashboard")
    print("  Server berjalan di http://127.0.0.1:5000")
    print("  ESP32 endpoint: POST http://127.0.0.1:5000/api/esp32")
    print("=" * 60)

    # Mulai background thread untuk simulasi data
    socketio.start_background_task(background_simulation)

    socketio.run(app, host='0.0.0.0', port=5000, debug=True,
                 use_reloader=False, allow_unsafe_werkzeug=True)

