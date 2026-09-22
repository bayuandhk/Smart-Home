"""
Smart Home HMI Dashboard - Dual Protocol Server
(Integrated with Dynamic Enterprise Zones, Bidirectional Control & POC Pager Adaptive Runtime)
"""

import asyncio
import json
import os
import random
import threading
import time
from functools import wraps
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_socketio import SocketIO
from models import (
    ControllerBoard,
    FunctionBlock,
    IOMapping,
    Project,
    WidgetNode,
    db,
    AutomationRule
)
from werkzeug.utils import secure_filename
import websockets

WS_LOOP = None

# ──────────────────────────────────────────────
# Inisialisasi Aplikasi Flask & Database SQLite
# ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'smart-home-pbl-secret-key'
app.config['SECRET_KEY'] = 'smart-home-pbl-secret-key'

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Jika tidak ada sesi 'logged_in', lempar paksa ke halaman login
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(
    basedir, 'smarthome_studio.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', transports=['polling'], allow_upgrades=False)

with app.app_context():
  db.create_all()
  try:
    with db.engine.connect() as conn:
      result = conn.execute(db.text("PRAGMA table_info(io_mappings)")).fetchall()
      cols = [row[1] for row in result]
      if "comm_type" not in cols:
        conn.execute(db.text("ALTER TABLE io_mappings ADD COLUMN comm_type VARCHAR(20) DEFAULT 'RELAY'"))
        conn.commit()
        print("[DATABASE] Migrasi: Kolom 'comm_type' berhasil ditambahkan ke io_mappings!")
  except Exception as e:
    print(f"[DATABASE] Migrasi error: {e}")
  print("[DATABASE] Skema tabel Studio IoT berhasil diinisialisasi!")

connected_devices = {}
last_known_status = {}

def is_hardware_panel(dev_id, ip=""):
    d = str(dev_id).lower()
    cip = str(ip)
    return (
        d.startswith("main") or
        d.startswith("panel") or
        d.startswith("master") or
        "panel" in d or
        "master" in d or
        "gateway" in d or
        cip in ["192.168.88.250", "192.168.88.253"]
    )

# Flag & State: Mode Murni Hardware (Virtual Panel Dimatikan)
VIRTUAL_PANEL_ENABLED = False
REAL_PANEL_CONNECTED = True
virtual_state = {
    "power": {
        "voltage": 0.0,
        "current": 0.0,
        "power": 0.0,
        "energy": 0.0,
        "frequency": 0.0,
        "pf": 0.0,
    },
    "relay": [False, False, False, False, False, False, False, False],
    "alarm": {
        "fire": False,
        "gas": False,
        "pir": False,
        "smoke": False,
        "door": False,
        "flood": False,
    },
    "environment": {
        "temperature": 0.0,
        "humidity": 0.0,
        "gas_ppm": 0.0
    },
    "instances": {}
}
last_known_alarms = {
    "fire": False,
    "gas": False,
    "pir": False,
    "smoke": False,
    "door": False,
    "flood": False,
}

# ==========================================
# I/O DEFINITION & MAPPING: SLAVE ESP32-S3
# ==========================================
SLAVE_IO_MAP = {
    # 1. Digital Normal I/O (NIO)
    "NIO1": 35, "NIO2": 36, "NIO3": 37, "NIO4": 38,
    "NIO5": 39, "NIO6": 40, "NIO7": 41, "NIO8": 42,
    # 2. Analog Inputs (AI)
    "AI1": 1, "AI2": 2, "AI3": 3, "AI4": 7,
    # 3. Communication & Bus I/O
    "UART1_RX": 4, "UART1_TX": 5, "UART1_CTRL": 6,
    "I2C_SDA": 8, "I2C_SCL": 9,
    "SPI_CS": 10, "SPI_MOSI": 11, "SPI_CLK": 12, "SPI_MISO": 13, "SPI_INT": 14,
    "RS485_TX": 17, "RS485_RX": 18,
    # 4. Spare GPIOs
    "GPIO15": 15, "GPIO16": 16, "GPIO19": 19, "GPIO20": 20, "GPIO21": 21,
    "GPIO45": 45, "GPIO46": 46, "GPIO47": 47, "GPIO48": 48,
}
SLAVE_PIN_TO_NAME = {v: k for k, v in SLAVE_IO_MAP.items()}

def get_io_name(pin_num):
    try:
        p = int(pin_num)
        name = SLAVE_PIN_TO_NAME.get(p)
        return f"{name} (GPIO {p})" if name else f"GPIO {p}"
    except:
        return str(pin_num)

@app.context_processor
def inject_io_helpers():
    return dict(get_io_name=get_io_name, SLAVE_IO_MAP=SLAVE_IO_MAP, SLAVE_PIN_TO_NAME=SLAVE_PIN_TO_NAME)

app.jinja_env.globals['get_io_name'] = get_io_name

# ==========================================
# MIDDLEWARE CORE: RUNTIME & BINDING REGISTRY
# ==========================================

# Menyimpan state terkini dari seluruh variabel sistem
RUNTIME_REGISTRY = {
    "sensors": {},
    "actuators": {},
    "alarms": {},
    "telemetry": {},
    "system": {}
}


def runtime_set_sensor(name, value):
    """Menyimpan nilai sensor ke Runtime Registry."""
    if not name:
        return

    RUNTIME_REGISTRY["sensors"][str(name)] = value


def runtime_get_sensor(name, default=None):
    """Mengambil nilai sensor dari Runtime Registry."""
    if not name:
        return default

    return RUNTIME_REGISTRY["sensors"].get(str(name), default)


def runtime_set_actuator(name, value):
    """Menyimpan state actuator ke Runtime Registry."""
    if not name:
        return

    RUNTIME_REGISTRY["actuators"][str(name)] = bool(value)


def runtime_get_actuator(name, default=False):
    """Mengambil state actuator dari Runtime Registry."""
    if not name:
        return default

    return RUNTIME_REGISTRY["actuators"].get(
        str(name),
        default
    )


def runtime_set_alarm(name, value):
    """Menyimpan state alarm ke Runtime Registry."""
    if not name:
        return

    RUNTIME_REGISTRY["alarms"][str(name)] = bool(value)


def runtime_get_alarm(name, default=False):
    """Mengambil state alarm dari Runtime Registry."""
    if not name:
        return default

    return RUNTIME_REGISTRY["alarms"].get(
        str(name),
        default
    )


def runtime_set_telemetry(name, value):
    """Menyimpan nilai telemetry ke Runtime Registry."""
    if not name:
        return

    RUNTIME_REGISTRY["telemetry"][str(name)] = value


def runtime_get_telemetry(name, default=None):
    """Mengambil nilai telemetry dari Runtime Registry."""
    if not name:
        return default

    return RUNTIME_REGISTRY["telemetry"].get(
        str(name),
        default
    )


def runtime_set_system(name, value):
    """Menyimpan state sistem internal."""
    if not name:
        return

    RUNTIME_REGISTRY["system"][str(name)] = value


def runtime_get_system(name, default=None):
    """Mengambil state sistem internal."""
    if not name:
        return default

    return RUNTIME_REGISTRY["system"].get(
        str(name),
        default
    )

# INBOUND: Mapping dari (slave_id, sensor_type, parameter) -> Nama Variabel Runtime
INBOUND_BINDING = {
    (1, "DHT11", "temperature"): "env_suhu_kamar",
    (1, "DHT11", "humidity"): "env_humidity_kamar"
}

# OUTBOUND: Mapping dari Nama Variabel Runtime -> Alamat Hardware Fisik
OUTBOUND_BINDING = {
    "exhaust": {"slave_id": 2, "type": "relay", "channel": 2},
    "lampu_utama": {"slave_id": 2, "type": "relay", "channel": 0},
    "gate_2": {"slave_id": 2, "type": "relay", "channel": 1},  # Sesuaikan channel
    "lampu_10": {"slave_id": 2, "type": "relay", "channel": 3} # Sesuaikan channel
}

@app.route('/api/automation/<int:project_id>', methods=['POST'])
@login_required
def add_automation_rule(project_id):
    data = request.json
    try:
        new_rule = AutomationRule(
            project_id=project_id,
            rule_name=data['rule_name'],
            condition_widget=data['condition_widget'],
            condition_operator=data['condition_operator'],
            condition_value=data['condition_value'],
            action_widget=data['action_widget'],
            action_state=data['action_state']
        )
        db.session.add(new_rule)
        db.session.commit()
        return jsonify({"status": "success", "message": "Aturan automasi ditambahkan."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/automation/delete/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_automation_rule(rule_id):
    try:
        rule = AutomationRule.query.get_or_404(rule_id)
        db.session.delete(rule)
        db.session.commit()
        return jsonify({"status": "success", "message": "Aturan berhasil dihapus."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Jika pengguna sudah login, langsung arahkan ke Dashboard
    if 'logged_in' in session:
        return redirect(url_for('dashboard')) # Pastikan fungsi route '/' Anda bernama 'dashboard' atau sesuaikan namanya

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Kredensial sementara (Admin)
        if username == 'admin' and password == 'admin':
            session['logged_in'] = True
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Username atau password salah!")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ──────────────────────────────────────────────
# Pengepakan Data untuk Web UI & Lokasi
# ──────────────────────────────────────────────
def get_web_payload(status_payload):
  try:
    relays = status_payload.get('relay', [])
    return {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'telemetry': status_payload.get('power', {}),
        'environment': status_payload.get('environment', {}),
        'instances': status_payload.get('instances', {}),
        'relays': {
            f'relay_{i}': relays[i] if len(relays) > i else False
            for i in range(8)
        },
        'alarms': status_payload.get(
            'alarm', {}
        ),
        'sensors': {
            'dapur': {
                'gas': 'ACTIVE'
                if status_payload.get('alarm', {}).get('gas')
                else 'AMAN'
            },
            'ruang_tamu': {
                'pir': 'ACTIVE'
                if status_payload.get('alarm', {}).get('pir')
                else 'AMAN'
            },
            'kamar': {
                'fire': 'ACTIVE'
                if status_payload.get('alarm', {}).get('fire')
                else 'AMAN'
            },
        },
    }
  except Exception as e:
    print(f"[WS-5000] Error mapping payload: {e}")
    return {}

def get_alarm_location(alarms):
  if alarms.get("fire"): return "Bedroom"
  if alarms.get("gas"): return "Kitchen"
  if alarms.get("pir"): return "Living Room"
  if alarms.get("door"): return "Gate"
  return "Unknown"

# ──────────────────────────────────────────────
# Task: Virtual Main Panel (DINONAKTIFKAN: Mode Hardware Asli)
# ──────────────────────────────────────────────
async def virtual_panel_task():
  """Virtual Panel dinonaktifkan: Sistem beroperasi murni menggunakan data sensor fisik riil."""
  print("\033[93m[SYSTEM] 🚫 Virtual Panel DIMATIKAN. Sistem beroperasi 100% menggunakan sensor & hardware fisik riil.\033[0m")
  return

# ──────────────────────────────────────────────
# Task: ST Engine - Automation Scan Cycle
# ──────────────────────────────────────────────
async def st_engine_task():
    global WS_LOOP, virtual_state
    print("[ST ENGINE] Aktif. Memantau aturan automasi setiap 1 detik...")
    
    while True:
        await asyncio.sleep(1) # Siklus pemindaian 1 detik
        
        with app.app_context():
            # Baca semua aturan yang berstatus aktif
            rules = AutomationRule.query.filter_by(is_active=True).all()
            
            for rule in rules:
                # 1. Baca nilai sensor saat ini dari Memory Environment
                current_val = runtime_get_sensor(rule.condition_widget)
                if current_val is None:
                    continue # Lewati jika sensor belum pernah mengirim data
                    
                # 2. Evaluasi Logika (IF)
                is_met = False
                if rule.condition_operator == '>': is_met = current_val > rule.condition_value
                elif rule.condition_operator == '<': is_met = current_val < rule.condition_value
                elif rule.condition_operator == '==': is_met = current_val == rule.condition_value
                    
                # 3. Eksekusi Aksi (THEN) dengan Anti-Spam
                if is_met and rule.last_triggered_state != True:
                    print(f"\n[ST ENGINE] ⚙️ Rule '{rule.rule_name}' TERPICU! ({current_val} {rule.condition_operator} {rule.condition_value})")
                    
                    rule.last_triggered_state = True
                    db.session.commit()
                    
                    # --- EKSEKUSI HARDWARE-LEVEL (GPIO) ---
                    try:
                        raw_action = rule.action_widget
                        if str(raw_action) in SLAVE_IO_MAP:
                            gpio_pin = SLAVE_IO_MAP[str(raw_action)]
                        else:
                            gpio_pin = int(raw_action) # Membaca angka pin GPIO (misal: 35)
                        target_state = rule.action_state
                        
                        # Lakukan Reverse-Lookup untuk menyinkronkan animasi UI di Web
                        channel_idx = None
                        pager_var_name = f"gpio_{gpio_pin}"
                        
                        mapping = IOMapping.query.filter_by(gpio_pin=gpio_pin).first()
                        if mapping:
                            channel_idx = mapping.channel_index
                            w = WidgetNode.query.get(mapping.widget_id)
                            if w: pager_var_name = w.label_name
                            
                        # 1. Update Animasi Web Dashboard (Jika pin tersebut ada di kanvas HMI)
                        if channel_idx is not None:
                            runtime_set_actuator(pager_var_name, target_state)
                            virtual_state["relay"][channel_idx] = target_state
                            socketio.emit("update_status", get_web_payload(virtual_state))
                            
                        # 2. Dispatch Perintah Fisik Langsung ke ESP32 berdasarkan GPIO & Channel
                        io_name = SLAVE_PIN_TO_NAME.get(gpio_pin, f"D{gpio_pin}")
                        
                        # Pastikan channel_idx tersedia untuk protokol RELAY_8CH
                        if channel_idx is None:
                            if io_name.startswith("NIO"):
                                try:
                                    channel_idx = int(io_name.replace("NIO", "")) - 1
                                except:
                                    channel_idx = 0
                            else:
                                channel_idx = 0

                        cmd_payload = json.dumps({
                            "type": "hardware_command",
                            "target": "main_panel_01",
                            "payload": {
                                "slave_id": 1,
                                "module_type": "RELAY_8CH",
                                "channel": channel_idx,
                                "port": io_name,
                                "pin": gpio_pin,
                                "state": bool(target_state)
                            }
                        })
                        
                        # 3. Siarkan Payload ke Hardware (Main Panel/Slave) & Pager Mobile
                        for d_id, ws in list(connected_devices.items()):
                            if is_hardware_panel(d_id):
                                try:
                                    await ws.send(cmd_payload)
                                    print(f"  ↳ 📤 [ST ENGINE] Dispatch ke Hardware ({d_id}): Slave 1, Ch {channel_idx} ({io_name}) -> {bool(target_state)}")
                                except Exception as err:
                                    print(f"  ↳ ❌ [ST ENGINE] Gagal dispatch ke {d_id}: {err}")
                            elif d_id.startswith("pager"):
                                event_msg = json.dumps({"type": "status_update", "from": "server", "to": "all", "payload": {"variable": pager_var_name, "value": target_state}})
                                try:
                                    await ws.send(event_msg)
                                except:
                                    pass
                                
                    except ValueError:
                        print(f"[ST ENGINE] ⚠️ Error: '{rule.action_widget}' bukan format GPIO yang valid.")

                # 4. Reset Kunci jika kondisi kembali normal
                elif not is_met and rule.last_triggered_state == True:
                    print(f"[ST ENGINE] ♻️ Rule '{rule.rule_name}' KEMBALI NORMAL.")
                    rule.last_triggered_state = False
                    db.session.commit()

# ──────────────────────────────────────────────
# Helper SSoT Hardware Manifest ESP32
# ──────────────────────────────────────────────
def generate_hardware_manifests(project_id=1):
    """Membangun JSON deploy_manifest (Sensor) dan command (Relay) sesuai format ESP32 SSoT."""
    proj = Project.query.get(project_id) if project_id else Project.query.first()
    if not proj:
        proj = Project.query.first()
    if not proj:
        return None, None

    all_widgets = WidgetNode.query.filter_by(project_id=proj.id).all()
    hw_instances = []
    hw_actuators = []

    for w in all_widgets:
        if not w.mapping:
            continue

        raw_pin = w.mapping.gpio_pin
        if isinstance(raw_pin, str) and raw_pin in SLAVE_IO_MAP:
            io_name = raw_pin
        else:
            try:
                p_int = int(raw_pin)
                io_name = SLAVE_PIN_TO_NAME.get(p_int, f"NIO{p_int}" if 1 <= p_int <= 8 else str(raw_pin))
            except (ValueError, TypeError):
                io_name = str(raw_pin)

        comm_type = getattr(w.mapping, 'comm_type', None) if w.mapping else None
        if not comm_type:
            if w.widget_type.startswith('SENSOR_'):
                comm_type = 'UART' if w.widget_type == 'SENSOR_POWER' else ('SPI' if w.widget_type in ['SENSOR_FIRE', 'SENSOR_PIR'] else 'I2C')
            else:
                comm_type = 'RELAY'

        if w.widget_type.startswith('SENSOR_'):
            hw_sensor_type = "UNKNOWN"
            sample_ms = 2000
            if w.widget_type == 'SENSOR_TEMP':
                hw_sensor_type = "DHT11"
                sample_ms = 2000
            elif w.widget_type == 'SENSOR_GAS':
                hw_sensor_type = "MQ_ANALOG"
                sample_ms = 1000
            elif w.widget_type == 'SENSOR_PIR':
                hw_sensor_type = "PIR_DIGITAL"
                sample_ms = 2000
            elif w.widget_type == 'SENSOR_POWER':
                hw_sensor_type = "PZEM"
                sample_ms = 2000
            elif w.widget_type == 'SENSOR_FIRE':
                hw_sensor_type = "FIRE_DIGITAL"
                sample_ms = 1000

            hw_instances.append({
                "instance_id": w.label_name,
                "sensor_type": hw_sensor_type,
                "port": io_name,
                "sample_ms": sample_ms
            })

        elif w.widget_type in ['LAMP_INDICATOR', 'PUMP_CONTROL', 'GATE_CONTROL', 'FAN_CONTROL', 'SMART_PLUG']:
            channel_idx = w.mapping.channel_index
            is_active_low = w.mapping.active_low if hasattr(w.mapping, 'active_low') else False
            trigger_level = 0 if is_active_low else 1
            hw_actuators.append({
                "instance_id": w.label_name,
                "module_type": "RELAY",
                "channel": channel_idx,
                "port": io_name,
                "pin": raw_pin,
                "active_level": trigger_level,
                "initial_state": False
            })

    deploy_manifest = {
        "type": "deploy_manifest",
        "target": "main_panel_01",
        "version": 1,
        "slave_id": 1,
        "instances": hw_instances
    }

    command_manifest = {
        "type": "command",
        "target": "main_panel_01",
        "slave_id": 1,
        "actuators": hw_actuators
    }

    return deploy_manifest, command_manifest


# ──────────────────────────────────────────────
# Route Persistensi & Compiler Studio
# ──────────────────────────────────────────────
@app.route('/api/save_studio/<int:project_id>', methods=['POST'])
@login_required
def save_studio_state(project_id):
  """Menyimpan layout dan mem-push secara dinamis ke Pager (Live Reload)."""
  try:
    data = request.json
    proj = Project.query.get_or_404(project_id)

    if 'background_image' in data:
      proj.background_image = data['background_image']

    board = ControllerBoard.query.filter_by(project_id=proj.id).first()
    if not board:
      board = ControllerBoard(project_id=proj.id, device_id="panel01")
      db.session.add(board)
    board.board_name = data.get('board_name', 'ESP32-WROOM-32')

    fb = FunctionBlock.query.filter_by(board_id=board.id).first()
    if not fb:
      fb = FunctionBlock(board_id=board.id, fb_identifier="FB_RELAY_1")
      db.session.add(fb)
    fb.module_type = data.get('relay_type', 'RELAY_8CH')
    fb.total_channels = int(data.get('total_channels', 8))

    WidgetNode.query.filter_by(project_id=proj.id).delete()
    IOMapping.query.filter_by(fb_id=fb.id).delete()

    for idx, w_item in enumerate(data.get('widgets', [])):
      new_w = WidgetNode(
          project_id=proj.id,
          widget_id=w_item['widget_id'],
          label_name=w_item['label_name'],
          zone_name=w_item.get('zone_name', 'Area Umum'),
          widget_type=w_item['widget_type'],
          pos_x=float(w_item['pos_x']),
          pos_y=float(w_item['pos_y']),
      )
      db.session.add(new_w)
      db.session.flush()

      if 'mapping' in w_item and w_item['mapping']:
        raw_pin = w_item['mapping']['gpio_pin']
        if isinstance(raw_pin, str) and raw_pin in SLAVE_IO_MAP:
          resolved_pin = SLAVE_IO_MAP[raw_pin]
        else:
          try:
            resolved_pin = int(raw_pin)
          except:
            resolved_pin = 35

        comm_type = w_item['mapping'].get('comm_type')
        if not comm_type:
          if w_item['widget_type'].startswith('SENSOR_'):
            comm_type = 'UART' if w_item['widget_type'] == 'SENSOR_POWER' else ('SPI' if w_item['widget_type'] in ['SENSOR_FIRE', 'SENSOR_PIR'] else 'I2C')
          else:
            comm_type = 'RELAY'

        new_m = IOMapping(
            widget_id=new_w.id,
            fb_id=fb.id,
            channel_index=int(w_item['mapping']['channel_index']),
            gpio_pin=resolved_pin,
            active_low=bool(w_item['mapping'].get('active_low', False)),
            array_order=idx,
            comm_type=comm_type,
        )
        db.session.add(new_m)

    proj.updated_at = int(time.time())
    db.session.commit()

    # =====================================================================
    # LIVE RELOAD & SSOT MANIFEST DEPLOYMENT
    # =====================================================================
    try:
      global WS_LOOP
      if WS_LOOP and WS_LOOP.is_running():
        all_widgets = WidgetNode.query.filter_by(project_id=proj.id).all()
        
        relay_items = []
        sensor_pages = []

        for idx, w in enumerate(all_widgets):
          # A. Kumpulkan data untuk Sinkronisasi UI (Pager)
          if w.widget_type in ['LAMP_INDICATOR', 'PUMP_CONTROL', 'GATE_CONTROL', 'FAN_CONTROL', 'SMART_PLUG']:
              ch = w.mapping.channel_index if w.mapping else 0
              is_on = virtual_state["relay"][ch] if 0 <= ch < len(virtual_state["relay"]) else False
              relay_items.append({"variable": w.label_name, "value": is_on})
          elif w.widget_type.startswith('SENSOR_'):
              sensor_pages.append({
                  "page_id": f"env_{w.label_name}",
                  "sensor_type": w.widget_type,
                  "title": w.zone_name.upper() if w.zone_name else "AREA UMUM"
              })

        # B. Dapatkan Hardware Manifest resmi (ESP32)
        deploy_manifest_dict, command_manifest_dict = generate_hardware_manifests(proj.id)

        # 1. Pesan untuk UI Web Dashboard
        msg_relay = json.dumps({"type": "runtime_list", "from": "server", "to": "all", "payload": {"relay": relay_items}})
        msg_sensor = json.dumps({"type": "runtime_sensor_manifest", "from": "server", "to": "all", "payload": {"sensor_pages": sensor_pages}})
        
        # 2. SSoT Manifest Resmi untuk Slave 1 (Khusus Sensor)
        deploy_manifest = json.dumps(deploy_manifest_dict)

        # 3. Manifest Command Khusus untuk Slave 2 (Khusus Relay/Aktuator)
        command_manifest = json.dumps(command_manifest_dict)

        # Broadcast via WebSocket
        for d_id, ws in list(connected_devices.items()):
          if d_id.startswith("pager") or "pager" in d_id.lower():
            asyncio.run_coroutine_threadsafe(ws.send(msg_relay), WS_LOOP)
            asyncio.run_coroutine_threadsafe(ws.send(msg_sensor), WS_LOOP)
          elif d_id.startswith("main_panel") or d_id.startswith("panel"):
            # Tembakkan KEDUA manifest ke Main Panel sebagai Gateway
            asyncio.run_coroutine_threadsafe(ws.send(deploy_manifest), WS_LOOP)
            asyncio.run_coroutine_threadsafe(ws.send(command_manifest), WS_LOOP)
            
        print("[SERVER] ⚡ Layout disimpan! Dual Manifest (Sensor & Relay) dikirim ke Main Panel.")
        print(f"  ↳ Sensor Manifest: {deploy_manifest}")
        print(f"  ↳ Relay Command  : {command_manifest}")
    except Exception as e:
      print(f"[SERVER] ⚠️ Gagal push live reload/manifest: {e}")
    # =====================================================================

    return jsonify({"status": "success", "message": "Perubahan Studio berhasil disimpan ke SQLite!"}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"status": "error", "message": f"Gagal menyimpan ke database: {str(e)}"}), 500

@app.route('/api/generate_json/<int:project_id>', methods=['GET'])
@login_required
def generate_project_json(project_id):
  """ENGINE COMPILER: Menerjemahkan wiring visual & zona menjadi format Topologi Ringkas"""
  try:
    proj = Project.query.get_or_404(project_id)
    board = ControllerBoard.query.filter_by(project_id=proj.id).first()
    if not board: 
        return jsonify({"status": "error", "message": "Controller board belum dikonfigurasi!"}), 400

    all_widgets = WidgetNode.query.filter_by(project_id=proj.id).all()
    
    tabel_control = []
    tabel_sensor = []

    for w in all_widgets:
      # Ambil data mapping (GPIO & Channel) jika widget sudah di-mapping
      channel_idx = w.mapping.channel_index if w.mapping else -1
      gpio_pin = w.mapping.gpio_pin if w.mapping else -1
      io_label = SLAVE_PIN_TO_NAME.get(gpio_pin, f"GPIO{gpio_pin}") if gpio_pin != -1 else "NONE"
      
      comm_type = getattr(w.mapping, 'comm_type', None) if w.mapping else None
      if not comm_type:
        if w.widget_type.startswith('SENSOR_'):
          comm_type = 'UART' if w.widget_type == 'SENSOR_POWER' else ('SPI' if w.widget_type in ['SENSOR_FIRE', 'SENSOR_PIR'] else 'I2C')
        else:
          comm_type = 'RELAY'

      # Struktur dasar setiap node/komponen
      widget_data = {
          "name": w.label_name,
          "type": w.widget_type,
          "comm_type": comm_type,
          "gpio": gpio_pin,
          "io_label": io_label,
          "zone": w.zone_name if hasattr(w, 'zone_name') else 'Area Umum'
      }

      # Pisahkan berdasarkan Tipe (Sensor vs Control)
      if w.widget_type.startswith('SENSOR_'):
          tabel_sensor.append(widget_data)
      else:
          # Jika Control/Output, tambahkan parameter channel relay
          widget_data["channel"] = channel_idx
          tabel_control.append(widget_data)

    # Urutkan tabel_control berdasarkan urutan channel relay agar rapi dibaca firmware
    tabel_control = sorted(tabel_control, key=lambda x: x.get('channel', 0))

    # Bentuk akhir JSON Tree yang simpel
    master_json = {
        "hardware_node": {
            "board_id": board.device_id,
            "controller": board.board_name
        },
        "monitoring": {
            "tabel_control": tabel_control,
            "tabel_sensor": tabel_sensor
        }
    }

    # Simpan history generate ke SQLite
    proj.generated_json = json.dumps(master_json)
    proj.updated_at = int(time.time())
    db.session.commit()
    
    return jsonify(master_json), 200
  except Exception as e:
    return jsonify({"status": "error", "message": f"Gagal mengompilasi JSON: {str(e)}"}), 500

@app.route('/api/manifest', methods=['GET'])
@app.route('/api/manifest/<int:project_id>', methods=['GET'])
def get_manifest_api(project_id=1):
  """Menampilkan JSON deploy_manifest dan command_manifest yang dikirim ke ESP32."""
  try:
    dep_m, cmd_m = generate_hardware_manifests(project_id)
    return jsonify({
        "status": "success",
        "deploy_manifest": dep_m,
        "command_manifest": cmd_m
    }), 200
  except Exception as e:
    return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/studio/<int:project_id>')
@login_required
def open_studio(project_id):
  proj = Project.query.get_or_404(project_id)
  board = ControllerBoard.query.filter_by(project_id=proj.id).first()
  fb_list = FunctionBlock.query.filter_by(board_id=board.id).all() if board else []
  widgets = WidgetNode.query.filter_by(project_id=proj.id).all()
  rules = AutomationRule.query.filter_by(project_id=proj.id).all()

  widgets_data = []
  for w in widgets:
    icons_map = {
        'LAMP_INDICATOR': '💡', 'PUMP_CONTROL': '💧', 'GATE_CONTROL': '🚪',
        'FAN_CONTROL': '🌀', 'SMART_PLUG': '🔌', 'SENSOR_FIRE': '🔥',
        'SENSOR_GAS': '💨', 'SENSOR_PIR': '🏃', 'SENSOR_TEMP': '🌡️', 'SENSOR_POWER': '⚡'
    }
    icon_str = icons_map.get(w.widget_type, '◉')
    comm_type = getattr(w.mapping, 'comm_type', None) if w.mapping else None
    if not comm_type:
      if w.widget_type.startswith('SENSOR_'):
        comm_type = 'UART' if w.widget_type == 'SENSOR_POWER' else ('SPI' if w.widget_type in ['SENSOR_FIRE', 'SENSOR_PIR'] else 'I2C')
      else:
        comm_type = 'RELAY'

    widgets_data.append({
        "id": f"w_{w.id}",
        "widget_id": w.widget_id,
        "label_name": w.label_name,
        "zone_name": w.zone_name if hasattr(w, 'zone_name') else 'Area Umum',
        "widget_type": w.widget_type,
        "pos_x": w.pos_x,
        "pos_y": w.pos_y,
        "icon": icon_str,
        "mapping": {
            "channel_index": w.mapping.channel_index if w.mapping else 0,
            "gpio_pin": w.mapping.gpio_pin if w.mapping else 23,
            "active_low": w.mapping.active_low if (w.mapping and hasattr(w.mapping, 'active_low')) else False,
            "comm_type": comm_type,
        },
    })

  return render_template(
      'studio.html',
      project=proj, board=board, function_blocks=fb_list,
      widgets_json=json.dumps(widgets_data),
      rules=rules
  )

@app.route('/api/upload_denah/<int:project_id>', methods=['POST'])
@login_required
def upload_denah(project_id):
  try:
    if 'file' not in request.files: return jsonify({"status": "error", "message": "Tidak ada file yang dipilih!"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"status": "error", "message": "Nama file tidak boleh kosong!"}), 400

    custom_label = request.form.get('label', 'Denah Custom').strip().replace(' ', '_').replace('/', '_')
    if not custom_label: custom_label = "Denah_Custom"

    allowed_ext = {'png', 'jpg', 'jpeg', 'webp', 'svg'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in allowed_ext: return jsonify({"status": "error", "message": "Format tidak didukung! Gunakan PNG, JPG, WEBP, atau SVG."}), 400

    filename = secure_filename(f"denah_project_{project_id}_{custom_label}_{int(time.time())}.{ext}")
    upload_folder = os.path.join(basedir, 'static', 'images')
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)

    image_url = f"/static/images/{filename}"
    proj = Project.query.get_or_404(project_id)
    proj.background_image = image_url
    db.session.commit()

    return jsonify({"status": "success", "message": "Denah berhasil diunggah!", "url": image_url, "label": request.form.get('label', 'Denah Custom').strip()}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/delete_denah/<int:project_id>', methods=['DELETE', 'POST'])
@login_required
def delete_denah(project_id):
  try:
    proj = Project.query.get_or_404(project_id)
    current_img = proj.background_image

    if current_img and current_img.startswith('/static/images/denah_project_'):
      filename = current_img.split('/')[-1]
      file_path = os.path.join(basedir, 'static', 'images', filename)
      if os.path.exists(file_path):
        try: os.remove(file_path)
        except Exception as e: print(f"[SERVER] Gagal menghapus file fisik: {e}")

    default_url = "/static/images/denah_rumah.png"
    proj.background_image = default_url
    db.session.commit()

    return jsonify({"status": "success", "message": "Denah kustom berhasil dihapus. Kembali ke default.", "url": default_url}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/seed_test')
@login_required
def seed_test_project():
  try:
    Project.query.delete()
    proj = Project(name="Smart Home Lantai 1", domain_type="smarthome")
    db.session.add(proj)
    db.session.commit()
    return jsonify({"status": "success", "message": "Silakan atur manual di Studio.", "project_id": proj.id}), 200
  except Exception as e:
    db.session.rollback()
    return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
@login_required
def dashboard():
  proj = Project.query.first()
  widgets = WidgetNode.query.filter_by(project_id=proj.id).all() if proj else []

  widgets_data = []
  # Tambahkan kamus ikon ini
  icons_map = {
      'LAMP_INDICATOR': '💡', 'PUMP_CONTROL': '💧', 'GATE_CONTROL': '🚪',
      'FAN_CONTROL': '🌀', 'SMART_PLUG': '🔌', 'SENSOR_FIRE': '🔥',
      'SENSOR_GAS': '💨', 'SENSOR_PIR': '🏃', 'SENSOR_TEMP': '🌡️', 'SENSOR_POWER': '⚡'
  }
  
  for w in widgets:
    # Ambil ikon dari kamus, jika tidak ada gunakan '◉'
    icon_str = icons_map.get(w.widget_type, '◉')
    
    widgets_data.append({
        'id': f'w_{w.id}', 'widget_id': w.widget_id, 'label_name': w.label_name,
        'zone_name': w.zone_name if hasattr(w, 'zone_name') else 'Area Umum',
        'widget_type': w.widget_type, 'icon': icon_str,
        'mapping': {'channel_index': w.mapping.channel_index if w.mapping else 0, 'gpio_pin': w.mapping.gpio_pin if w.mapping else 23},
    })

  return render_template('index.html', project=proj, widgets=widgets, widgets_json=json.dumps(widgets_data))

@socketio.on('connect')
def handle_web_connect():
  if last_known_status: socketio.emit('update_status', get_web_payload(last_known_status))

@socketio.on('trigger_emergency')
def handle_web_emergency(data):
  global last_known_alarms, virtual_state, WS_LOOP
  last_known_alarms["fire"] = True
  if "alarm" in virtual_state: virtual_state["alarm"]["fire"] = True
  socketio.emit('update_status', get_web_payload(virtual_state))
  socketio.emit('alarm_update', last_known_alarms)
  alarm_payload = last_known_alarms.copy()
  alarm_payload["location"] = "Bedroom"
  msg_str = json.dumps({"type": "alarm_update", "from": "panel01", "to": "all", "timestamp": int(time.time()), "payload": alarm_payload})
  try:
    if WS_LOOP and WS_LOOP.is_running():
      for d_id, ws in list(connected_devices.items()): asyncio.run_coroutine_threadsafe(ws.send(msg_str), WS_LOOP)
  except Exception as e:
    print(f"[ERROR] Emergency trigger gagal: {e}")

@socketio.on('alarm_ack_web')
def handle_web_ack(data):
  alarm_name = data.get("alarm", "")
  global last_known_alarms, virtual_state, WS_LOOP
  if alarm_name in last_known_alarms: last_known_alarms[alarm_name] = False
  if "alarm" in virtual_state and alarm_name in virtual_state["alarm"]: virtual_state["alarm"][alarm_name] = False
  socketio.emit('update_status', get_web_payload(virtual_state))
  socketio.emit('alarm_update', last_known_alarms)
  clear_payload = last_known_alarms.copy()
  clear_payload["location"] = "Aman"
  msg_str = json.dumps({"type": "alarm_update", "from": "panel01", "to": "all", "timestamp": int(time.time()), "payload": clear_payload})
  try:
    if WS_LOOP and WS_LOOP.is_running():
      for d_id, ws in list(connected_devices.items()): asyncio.run_coroutine_threadsafe(ws.send(msg_str), WS_LOOP)
  except Exception as e:
    print(f"[ERROR] Clear alarm gagal: {e}")

async def push_relay_to_connected_clients(payload_esp, ch, state, target_vars, relay_items):
    for d_id, ws in list(connected_devices.items()):
        # 1. Kirim ke hardware fisik (Main Panel)
        if is_hardware_panel(d_id):
            try:
                await ws.send(payload_esp)
                print(f"\033[95m[OUTBOUND] 🕹️ Command dikirim ke Hardware ({d_id}) | Channel {ch} = {'ON' if state else 'OFF'}\033[0m")
            except Exception as err:
                print(f"[OUTBOUND] ⚠️ Gagal kirim ke hardware {d_id}: {err}")
        
        # 2. Kirim ke Pager (semua device yang bukan hardware panel atau membawa nama pager)
        if not is_hardware_panel(d_id) or "pager" in str(d_id).lower():
            # Rakit paket presisi sesuai spesifikasi SmartHome Pager WebSocket Protocol v1.0
            primary_var = target_vars[0] if target_vars else f"relay_{ch}"
            pkts_to_send = [
                # A. Paket status SCS v1.0 resmi (Spesifikasi: to: pager01/d_id, payload.relay boolean)
                json.dumps({
                    "type": "status",
                    "from": "server",
                    "to": d_id,
                    "timestamp": int(time.time()),
                    "payload": virtual_state
                }),
                # B. Paket status alternatif (from: panel01)
                json.dumps({
                    "type": "status",
                    "from": "panel01",
                    "to": d_id,
                    "timestamp": int(time.time()),
                    "payload": virtual_state
                }),
                # C. Paket runtime_list persis seperti saat boot awal
                json.dumps({
                    "type": "runtime_list",
                    "from": "server",
                    "to": d_id,
                    "payload": {"relay": relay_items}
                }),
                # D. Paket status_update untuk variabel aktuator utama (boolean & integer)
                json.dumps({
                    "type": "status_update",
                    "from": "server",
                    "to": d_id,
                    "payload": {"variable": primary_var, "value": state}
                }),
                json.dumps({
                    "type": "status_update",
                    "from": "server",
                    "to": d_id,
                    "payload": {"variable": f"relay_{ch}", "value": state}
                }),
                json.dumps({
                    "type": "status_update",
                    "from": "server",
                    "to": "all",
                    "payload": {"variable": primary_var, "value": state}
                }),
                json.dumps({
                    "type": "status_update",
                    "from": "server",
                    "to": "all",
                    "payload": {"variable": f"relay_{ch}", "value": state}
                }),
                # E. Paket relay_update
                json.dumps({
                    "type": "relay_update",
                    "from": "server",
                    "to": d_id,
                    "payload": {"channel": ch, "state": state, "variable": primary_var}
                })
            ]

            for pkt in pkts_to_send:
                try:
                    await ws.send(pkt)
                    await asyncio.sleep(0.008) # Jeda aman 8ms agar RX buffer ESP32 tidak overflow
                except Exception as err:
                    print(f"[OUTBOUND] ⚠️ Gagal kirim ke pager {d_id}: {err}")
            print(f"\033[94m[OUTBOUND] 📱 Status relay Ch-{ch} ({'ON' if state else 'OFF'}) disinkronkan ke Pager ({d_id})\033[0m")

@socketio.on('control_gate')
def handle_gate_control(data):
    handle_general_relay(data)

@socketio.on('control_relay')
def handle_general_relay(data):
    device = data.get('device', 'unknown') # Contoh: 'relay_1'
    state_action = data.get('state', 'TOGGLE')
    
    # Ekstrak nomor channel dari string
    try:
        channel = int(device.split('_')[1])
    except:
        channel = 0

    global virtual_state
    if not (0 <= channel < len(virtual_state["relay"])):
        print(f"[WARN] Channel relay {channel} di luar batas valid (0-{len(virtual_state['relay'])-1})")
        return

    if state_action == 'TOGGLE':
        current_state = virtual_state["relay"][channel]
        new_state = not current_state
    elif isinstance(state_action, str):
        new_state = state_action.upper() in ['OPEN', 'ON', '1', 'TRUE']
    else:
        new_state = bool(state_action)

    # 1. Cari variabel AKTIS AKTUATOR yang sesuai (jangan cocokkan dengan sensor!)
    ACTUATOR_TYPES = ['LAMP_INDICATOR', 'PUMP_CONTROL', 'GATE_CONTROL', 'FAN_CONTROL', 'SMART_PLUG']
    target_vars = []
    is_gate = (channel == 7)
    relay_items = []
    
    with app.app_context():
        proj = Project.query.first()
        all_widgets = WidgetNode.query.filter_by(project_id=proj.id).all() if proj else []
        for w in all_widgets:
            if w.widget_type in ACTUATOR_TYPES:
                ch = w.mapping.channel_index if w.mapping else 0
                arr_order = getattr(w.mapping, 'array_order', None)
                if ch == channel or arr_order == channel:
                    target_vars.append(w.label_name)
                    if w.widget_type == 'GATE_CONTROL':
                        is_gate = True

        # Jika belum ada yang cocok, periksa apakah hanya ada 1 widget aktuator di proyek
        if not target_vars:
            actuators = [w for w in all_widgets if w.widget_type in ACTUATOR_TYPES]
            if len(actuators) == 1:
                target_vars.append(actuators[0].label_name)
                if actuators[0].widget_type == 'GATE_CONTROL':
                    is_gate = True

        # Susun ulang relay_items dengan status terkini untuk sinkronisasi runtime_list Pager
        for w in all_widgets:
            if w.widget_type in ACTUATOR_TYPES:
                ch = w.mapping.channel_index if w.mapping else 0
                is_on = new_state if (ch == channel) else (virtual_state["relay"][ch] if 0 <= ch < len(virtual_state["relay"]) else False)
                relay_items.append({"variable": w.label_name, "value": is_on})

    # Tambahkan alias channel generic
    target_vars.extend([
        f"relay_{channel}",
        f"relay_{channel+1}",
        f"ch_{channel}"
    ])
    if is_gate:
        target_vars.extend(["gate", "door", "gate_4", "pintu", "gerbang"])

    # 2. Update State Internal Server & SEGERA Sinkronkan ke Web UI
    virtual_state["relay"][channel] = new_state
    if is_gate:
        virtual_state["alarm"]["door"] = new_state
    for v in target_vars:
        runtime_set_actuator(v, new_state)
    socketio.emit('update_status', get_web_payload(virtual_state))

    # 3. Rakit Payload untuk Main Panel ESP32 (Hardware Slave)
    payload_to_esp = json.dumps({
        "type": "hardware_command",
        "target": "main_panel_01",
        "payload": {
            "slave_id": 1,
            "module_type": "RELAY_8CH",
            "channel": channel,
            "state": new_state
        }
    })

    # 4. Tembakkan ke Hardware & Pager via Raw WebSocket secara aman dan sinkron
    global WS_LOOP
    if WS_LOOP and WS_LOOP.is_running() and connected_devices:
        asyncio.run_coroutine_threadsafe(
            push_relay_to_connected_clients(payload_to_esp, channel, new_state, target_vars, relay_items),
            WS_LOOP
        )

# ──────────────────────────────────────────────
# Router WebSocket SCS v1.0 & Task
# ──────────────────────────────────────────────
async def router_handler(websocket, *args):
  global REAL_PANEL_CONNECTED, virtual_state, last_known_status
  device_id = "unknown"
  client_ip = websocket.remote_address[0] if websocket.remote_address else "local"
  print(f"\033[94m[WS-8765] 🔌 TCP Connection dibuka dari IP: {client_ip}\033[0m")

  # Deteksi awal jika IP adalah Main Panel / Master
  if is_hardware_panel("main_panel_01", client_ip):
      device_id = "main_panel_01"
      connected_devices[device_id] = websocket
      REAL_PANEL_CONNECTED = True
      print(f"\033[92m[WS-8765] 🔗 Terdeteksi Main Panel/Master dari IP {client_ip}! Auto-register aktif.\033[0m")
      try:
          with app.app_context():
              dep_m, cmd_m = generate_hardware_manifests()
              if dep_m and dep_m.get("instances"):
                  dep_json = json.dumps(dep_m)
                  await websocket.send(dep_json)
                  print(f"[WS-8765] 📤 [AUTO-PUSH] deploy_manifest ke {device_id}: {dep_json}")
              if cmd_m and cmd_m.get("actuators"):
                  cmd_json = json.dumps(cmd_m)
                  await websocket.send(cmd_json)
                  print(f"[WS-8765] 📤 [AUTO-PUSH] command_manifest ke {device_id}: {cmd_json}")
      except Exception as ex:
          print(f"[WS-8765] ⚠️ Gagal auto-push awal ke {device_id}: {ex}")

  try:
    async for message in websocket:
      try:
        data = json.loads(message)
        msg_type = data.get("type", "unknown")
        sender = data.get("from", "unknown")
        target = data.get("to", "unknown")
        payload = data.get("payload", {})

        # Deteksi otomatis Main Panel jika sender belum membawa ID atau bernama master/panel
        if is_hardware_panel(sender, client_ip):
            if sender == "unknown":
                sender = "main_panel_01"
            device_id = sender
            connected_devices[device_id] = websocket
            REAL_PANEL_CONNECTED = True
        elif sender != "unknown" and sender not in connected_devices:
            device_id = sender
            connected_devices[device_id] = websocket
            print(f"\033[92m[WS-8765] 🔗 Register jalur koneksi: {device_id} ({client_ip})\033[0m")

        # TANGANI HEARTBEAT (Top-Level atau Nested) DENGAN LOG JELAS DI TERMINAL IDE
        if msg_type.lower() in ["heartbeat", "slave_heartbeat"] or (isinstance(payload, dict) and payload.get("type", "").lower() == "heartbeat"):
            src = sender if sender != "unknown" else f"Main Panel ({client_ip})"
            slave_info = ""
            if isinstance(payload, dict) and payload.get("slave_id"):
                slave_info = f" (Slave {payload.get('slave_id')})"
            print(f"\033[92m[WS-8765] 💓 Heartbeat diterima dari [{src}]{slave_info} (Online)\033[0m")
            if not REAL_PANEL_CONNECTED:
                REAL_PANEL_CONNECTED = True
                print("\033[93m[WS-8765] ⚡ HARDWARE PANEL ASLI TERHUBUNG! Mengambil alih dari Virtual Panel.\033[0m")
            continue

        if msg_type.lower() not in ["field_data", "heartbeat", "slave_heartbeat"]:
            print(f"\n[WS-8765] 📨 INCOMING dari [{sender}] -> ke [{target}] | Tipe: {msg_type.upper()}")
            if payload: print(f"         ↳ Payload: {json.dumps(payload)}")

        if msg_type == "hello":
          device_id = sender
          connected_devices[device_id] = websocket
          print(f"[WS-8765] 🟢 Handshake sukses! Perangkat terdaftar: {device_id} ({client_ip})")
          if sender.startswith("panel") or sender.startswith("main_panel"):
            REAL_PANEL_CONNECTED = True
            print("[WS-8765] ⚡ HARDWARE PANEL ASLI TERHUBUNG! Mengambil alih dari Virtual Panel.")

          await websocket.send(json.dumps({
              "type": "hello_ack", "from": "server", "to": device_id,
              "timestamp": int(time.time()), "payload": {"result": "success"},
          }))

          # PUSH MANIFEST RESMI KE MAIN PANEL SAAT BOOT / KONEKSI TERHUBUNG (jika belum terkirim via auto-register)
          if sender.startswith("panel") or sender.startswith("main_panel"):
            try:
              with app.app_context():
                dep_m, cmd_m = generate_hardware_manifests()
                if dep_m and dep_m.get("instances"):
                  dep_json = json.dumps(dep_m)
                  await websocket.send(dep_json)
                  print(f"[WS-8765] 📤 [BOOT-PUSH] deploy_manifest ke {device_id}: {dep_json}")
                if cmd_m and cmd_m.get("actuators"):
                  cmd_json = json.dumps(cmd_m)
                  await websocket.send(cmd_json)
                  print(f"[WS-8765] 📤 [BOOT-PUSH] command_manifest ke {device_id}: {cmd_json}")
            except Exception as ex:
              print(f"[WS-8765] ⚠️ Gagal push manifest awal ke {device_id}: {ex}")

          # PUSH DUA JALUR TERPISAH (Relay & Sensor Manifest) + INITIAL STATE KE PAGER
          if sender.startswith("pager") or "pager" in sender.lower():
            with app.app_context():
              proj = Project.query.first()
              all_widgets = WidgetNode.query.filter_by(project_id=proj.id).all() if proj else []
              
              relay_items = []
              sensor_pages = []
              
              for idx, w in enumerate(all_widgets):
                  if w.widget_type in ['LAMP_INDICATOR', 'PUMP_CONTROL', 'GATE_CONTROL', 'FAN_CONTROL', 'SMART_PLUG']:
                      ch = w.mapping.channel_index if w.mapping else 0
                      is_on = virtual_state["relay"][ch] if 0 <= ch < len(virtual_state["relay"]) else False
                      relay_items.append({"variable": w.label_name, "value": is_on})
                  elif w.widget_type.startswith('SENSOR_'):
                      sensor_pages.append({
                          "page_id": f"env_{w.label_name}",
                          "instance_id": w.label_name,
                          "variable": w.label_name,
                          "sensor_type": w.widget_type,
                          "title": w.zone_name.upper() if w.zone_name else "AREA UMUM"
                      })

              msg_relay = json.dumps({"type": "runtime_list", "from": "server", "to": device_id, "payload": {"relay": relay_items}})
              msg_sensor = json.dumps({"type": "runtime_sensor_manifest", 
                                       "from": "server", 
                                       "to": device_id, 
                                       "payload": {"sensor_pages": sensor_pages}})
              status_pkt = json.dumps({
                  "type": "status",
                  "from": "panel01",
                  "to": device_id,
                  "timestamp": int(time.time()),
                  "payload": virtual_state
              })

              await websocket.send(msg_relay)
              await websocket.send(msg_sensor)
              await websocket.send(status_pkt)
              print(f"[WS-8765] 📤 [POC] Push murni dari DB: Relay ({len(relay_items)} item) & Sensor Manifest ({len(sensor_pages)} page) & Status ke {device_id}")

              # Push nilai sensor terkini segera agar pager tidak menampilkan 0 saat baru terkoneksi
              for w in all_widgets:
                  if w.widget_type.startswith('SENSOR_'):
                      val = runtime_get_sensor(w.label_name)
                      if val is None:
                          val = 0.0

                      p_data = {"value": val, "val": val}
                      if w.widget_type == 'SENSOR_TEMP':
                          p_data["temperature"] = val
                          p_data["temp"] = val
                          p_data["humidity"] = virtual_state["environment"].get("humidity", 0.0)
                          p_data["hum"] = p_data["humidity"]
                      elif w.widget_type == 'SENSOR_GAS':
                          p_data["gas_ppm"] = val

                      init_sensor_msg = json.dumps({
                          "type": "sensor_update", "from": "server", "to": device_id,
                          "payload": {
                              "page_id": f"env_{w.label_name}",
                              "instance_id": w.label_name,
                              "variable": w.label_name,
                              "value": val,
                              "val": val,
                              "temperature": val if w.widget_type == 'SENSOR_TEMP' else 0,
                              "data": p_data
                          }
                      })
                      await websocket.send(init_sensor_msg)
              
        # =========================================================
        # 1. INBOUND / ETL EXTRACTION & LOAD (Dari Main Panel)
        # =========================================================
        elif msg_type.lower() == "field_data" or target == "unknown":

            if not REAL_PANEL_CONNECTED:
                REAL_PANEL_CONNECTED = True
                print("\033[93m[SERVER] ⚡ HARDWARE ASLI TERDETEKSI! Mematikan Virtual Panel...\033[0m")
            inner_type = payload.get("type", "unknown")
            slave_id = payload.get("slave_id", "N/A")
            
            # A. Tangani Handshake "Hello"
            if inner_type == "hello":
                slave_uid = payload.get("slave_uid", "Unknown")
                fw_version = payload.get("fw", "1.0.0")
                print(f"[MIDDLEWARE] 👋 Main Panel / Slave Terdaftar: {slave_uid} (FW: {fw_version})")
                continue
                
            # B. Tangani "Heartbeat" (Tampilkan jelas warna hijau di terminal)
            elif inner_type == "heartbeat":
                print(f"\033[92m[WS-8765] 💓 Heartbeat diterima dari Main Panel (Slave {slave_id} Online)\033[0m")
                continue
                
            # C. Tangani Data Sensor (etl_data) dengan Warna Cyan dan Hijaux
            elif inner_type == "etl_data":
                instance_id = payload.get("instance_id", "unknown_instance")
                sensor_type = payload.get("sensor_type", "UNKNOWN")
                values = payload.get("payload", {})
                
                print(f"\033[96m[ETL] 📥 Slave {slave_id} | Instance: {instance_id} ({sensor_type})\033[0m")
                
                primary_sensor_val = None
                if values:
                    # Prioritaskan key 'temperature', 'raw', atau 'value' jika ada
                    if "temperature" in values:
                        primary_sensor_val = values["temperature"]
                    elif "raw" in values:
                        primary_sensor_val = values["raw"]
                    elif "value" in values:
                        primary_sensor_val = values["value"]
                    else:
                        first_key = list(values.keys())[0]
                        primary_sensor_val = values[first_key]

                if primary_sensor_val is not None:
                    runtime_set_sensor(instance_id, primary_sensor_val)

                for key, val in values.items():
                    var_name = f"{instance_id}_{key}"
                    runtime_set_sensor(var_name, val)
                    print(f"   ├─ \033[92m{var_name}\033[0m = {val}")

                # 2. Sinkronisasi ke Web Dashboard HMI
                if "instances" not in virtual_state:
                    virtual_state["instances"] = {}

                # Simpan data spesifik per-instance sensor (misal: TEMP_1, TEMP_7)
                virtual_state["instances"][instance_id] = {
                    "val": primary_sensor_val,
                    "temperature": values.get("temperature"),
                    "humidity": values.get("humidity"),
                    "raw": values.get("raw") or values.get("gas_ppm"),
                    "sensor_type": sensor_type,
                    "updated_at": time.time()
                }

                if "temperature" in values:
                    virtual_state["environment"]["temperature"] = values["temperature"]
                if "humidity" in values:
                    virtual_state["environment"]["humidity"] = values["humidity"]
                
                # Tangkap dari key "raw" (kiriman ESP32) atau "gas_ppm"
                if "raw" in values:
                    virtual_state["environment"]["gas_ppm"] = values["raw"]
                elif "gas_ppm" in values:
                    virtual_state["environment"]["gas_ppm"] = values["gas_ppm"]
                # ----------------------------

                if "voltage" in values:
                    virtual_state["power"]["voltage"] = values["voltage"]
                if "power" in values:
                    virtual_state["power"]["power"] = values["power"]
                    
                last_known_status = virtual_state
                socketio.emit("update_status", get_web_payload(last_known_status))

                # =========================================================
                # 3. SINKRONISASI KE PAGER (Handheld Mobile Pager)
                # =========================================================
                pager_data = values.copy()
                if "raw" in pager_data and sensor_type == "MQ_ANALOG":
                    pager_data["gas_ppm"] = pager_data.pop("raw") 
                
                # Pastikan key 'value' dan 'val' SELALU terisi untuk parsing generik pager!
                if primary_sensor_val is not None:
                    pager_data["value"] = primary_sensor_val
                    pager_data["val"] = primary_sensor_val
                if "temperature" in pager_data and "temp" not in pager_data:
                    pager_data["temp"] = pager_data["temperature"]
                if "humidity" in pager_data and "hum" not in pager_data:
                    pager_data["hum"] = pager_data["humidity"]

                # 1. sensor_update dengan page_id "env_<instance_id>"
                msg_pager_env = json.dumps({
                    "type": "sensor_update",
                    "from": "server",
                    "to": "all",
                    "payload": {
                        "page_id": f"env_{instance_id}",
                        "instance_id": instance_id,
                        "variable": instance_id,
                        "value": primary_sensor_val,
                        "val": primary_sensor_val,
                        "temperature": pager_data.get("temperature", primary_sensor_val),
                        "humidity": pager_data.get("humidity", 0),
                        "data": pager_data
                    }
                })

                # 2. sensor_update dengan page_id "<instance_id>" langsung
                msg_pager_direct = json.dumps({
                    "type": "sensor_update",
                    "from": "server",
                    "to": "all",
                    "payload": {
                        "page_id": instance_id,
                        "instance_id": instance_id,
                        "variable": instance_id,
                        "value": primary_sensor_val,
                        "val": primary_sensor_val,
                        "temperature": pager_data.get("temperature", primary_sensor_val),
                        "humidity": pager_data.get("humidity", 0),
                        "data": pager_data
                    }
                })

                # 3. status_update untuk sinkronisasi variabel Pager
                msg_status_update = json.dumps({
                    "type": "status_update",
                    "from": "server",
                    "to": "all",
                    "payload": {
                        "variable": instance_id,
                        "value": primary_sensor_val
                    }
                })
                msg_status_update_env = json.dumps({
                    "type": "status_update",
                    "from": "server",
                    "to": "all",
                    "payload": {
                        "variable": f"env_{instance_id}",
                        "value": primary_sensor_val
                    }
                })

                # 4. status SCS v1.0 periodik/instan memuat virtual_state aktual
                # Broadcast ke seluruh Pager yang terhubung dengan alamat presisi
                for d_id, ws in list(connected_devices.items()):
                    if is_hardware_panel(d_id):
                        continue
                    try:
                        status_to_pager = json.dumps({
                            "type": "status",
                            "from": "server",
                            "to": d_id,
                            "timestamp": int(time.time()),
                            "payload": virtual_state
                        })
                        await ws.send(msg_pager_env)
                        await ws.send(msg_pager_direct)
                        await ws.send(msg_status_update)
                        await ws.send(status_to_pager)
                    except:
                        pass
               

        # =========================================================
        # 2. OUTBOUND / COMMAND DISPATCHER (Dari Pager / ST Engine)
        # =========================================================
        elif msg_type == "command" and target == "server":
            var_name = payload.get("variable")
            target_val = payload.get("value")

            print(f"\n[MIDDLEWARE] 🕹️ Menerima command logika: '{var_name}' -> {target_val}")

            # 1. Update Runtime Registry agar state tersinkronisasi
            runtime_set_actuator(var_name, target_val)

            channel_idx = None # <-- Menyiapkan variabel penampung channel

            # Update Virtual State untuk sinkronisasi Web HMI
            with app.app_context():
                proj = Project.query.first()
                w = WidgetNode.query.filter_by(label_name=var_name).first() if proj else None
                if w and w.mapping:
                    channel_idx = w.mapping.channel_index # <-- Ambil channel dari SQLite
                    if channel_idx < len(virtual_state["relay"]): 
                        virtual_state["relay"][channel_idx] = target_val
                else:
                    names = ["ruang_tamu", "kamar", "dapur", "garasi"]
                    if var_name in names: virtual_state["relay"][names.index(var_name)] = target_val

            last_known_status = virtual_state
            socketio.emit("update_status", get_web_payload(last_known_status))

            # Broadcast ke Pager agar indikator switch berubah
            event_push_msg = json.dumps({
                "type": "status_update", "from": "server", "to": "all",
                "payload": {"variable": var_name, "value": target_val},
            })
            for d_id, ws in list(connected_devices.items()):
                if not is_hardware_panel(d_id):
                    try: await ws.send(event_push_msg)
                    except: pass
            print(f"[WS-8765] ⚡ [POC EVENT-PUSH] Disiarkan status_update: {var_name}={target_val}")

            # 2. THE MISSING LINK FIX: Dispatch Dinamis ke Hardware
            if channel_idx is not None:
                # Merakit JSON sesuai standar instruksi aktuator fisik di Slave 1
                cmd_payload = json.dumps({
                    "type": "hardware_command",
                    "target": "main_panel_01",
                    "payload": {
                        "slave_id": 1,
                        "module_type": "RELAY_8CH",
                        "channel": channel_idx,
                        "state": target_val
                    }
                })

                # Dispatch (Kirim) perintah ke ESP32
                for d_id, ws in list(connected_devices.items()):
                    if is_hardware_panel(d_id):
                        try:
                            await ws.send(cmd_payload)
                            print(f"  ↳ 📤 Dispatch ke Hardware ({d_id}): Slave 1, Ch {channel_idx}")
                        except:
                            print(f"  ↳ ❌ Gagal Dispatch: Main Panel terputus!")
            else:
                print(f"  ↳ ⚠️ Command diabaikan: Variabel '{var_name}' belum di-mapping di SH Studio.")


        elif target == "all":
          for d_id, ws in list(connected_devices.items()):
            if d_id != sender:
              try: await ws.send(message)
              except: pass
          if msg_type == "status" and sender.startswith("panel"):
            last_known_status = payload
            socketio.emit("update_status", get_web_payload(last_known_status))
            current_alarms = last_known_status.get("alarm", {})
            global last_known_alarms
            if current_alarms != last_known_alarms:
              last_known_alarms = current_alarms.copy()
              alarm_payload = current_alarms.copy()
              alarm_payload["location"] = get_alarm_location(current_alarms)
              broadcast_str = json.dumps({
                  "type": "alarm_update", "from": "panel01", "to": "all",
                  "timestamp": int(time.time()), "payload": alarm_payload,
              })
              for d_id, ws in list(connected_devices.items()):
                if d_id != sender:
                  try: await ws.send(broadcast_str)
                  except: pass
              socketio.emit("alarm_update", current_alarms)

        elif target == "server" and msg_type == "alarm_ack":
          alarm_name = payload.get("alarm", "unknown")
          print(f"[WS-8765] 🔕 ACK ALARM diproses dari {sender} untuk alarm: {alarm_name}")
          if alarm_name in last_known_alarms: last_known_alarms[alarm_name] = False
          if "alarm" in virtual_state and alarm_name in virtual_state["alarm"]: virtual_state["alarm"][alarm_name] = False
          try:
              await websocket.send(json.dumps({
                  "type": "command_ack", "from": "server", "to": sender,
                  "payload": {"command": "alarm_ack", "result": "success"},
              }))
          except:
              pass
          last_known_status = virtual_state
          socketio.emit("update_status", get_web_payload(last_known_status))
          clear_payload = last_known_alarms.copy()
          clear_payload["location"] = "Aman"
          broadcast_str = json.dumps({
              "type": "alarm_update", "from": "panel01", "to": "all",
              "timestamp": int(time.time()), "payload": clear_payload,
          })
          for d_id, ws in list(connected_devices.items()):
            if d_id != sender:
              try: await ws.send(broadcast_str)
              except: pass

        elif not REAL_PANEL_CONNECTED and target == "server":
          state_changed = False
          if msg_type == "relay_toggle":
            idx = payload.get("relay", 0)
            print(f"[WS-8765] 💡 EKSEKUSI: Toggle Relay Ch-{idx} perintah dari {sender} (Mode Virtual)")
            if 0 <= idx < len(virtual_state["relay"]):
              virtual_state["relay"][idx] = not virtual_state["relay"][idx]
              state_changed = True
          elif msg_type == "gate_open":
            print(f"[WS-8765] 🚪 EKSEKUSI: Membuka Gerbang perintah dari {sender}")
            virtual_state["alarm"]["door"] = True
            state_changed = True
          elif msg_type == "gate_close":
            print(f"[WS-8765] 🚪 EKSEKUSI: Menutup Gerbang perintah dari {sender}")
            virtual_state["alarm"]["door"] = False
            state_changed = True

          if state_changed:
            last_known_status = virtual_state
            socketio.emit("update_status", get_web_payload(last_known_status))
            broadcast_msg = json.dumps({
                "type": "status", "from": "panel01", "to": "all",
                "timestamp": int(time.time()), "payload": virtual_state,
            })
            for d_id, ws in list(connected_devices.items()):
              try: await ws.send(broadcast_msg)
              except: pass

        elif target in connected_devices:
          print(f"[WS-8765] 🔀 ROUTING: Meneruskan pesan langsung ke [{target}]")
          await connected_devices[target].send(message)
        else:
          print(f"[WS-8765] ⚠️ PERINGATAN: Target [{target}] tidak ditemukan dalam daftar perangkat online!")

      except json.JSONDecodeError:
        print(f"[WS-8765] ❌ Error: Menerima paket non-JSON dari {client_ip}")
  except websockets.exceptions.ConnectionClosed:
    pass
  finally:
    if connected_devices.get(device_id) == websocket:
        del connected_devices[device_id]
        if is_hardware_panel(device_id, client_ip):
            print(f"[WS-8765] ⚠️ Hardware Panel/Master ({device_id}) terputus.")
    print(f"[WS-8765] 🔴 Perangkat terputus dari server: {device_id} ({client_ip})")

async def run_ws_server():
  global WS_LOOP
  WS_LOOP = asyncio.get_running_loop()
  print("[SERVER] SCS v1.0 Router siap di ws://192.168.88.254:8765 [MODE MURNI HARDWARE]")
  await websockets.serve(router_handler, "192.168.88.254", 8765, ping_interval=None)
  asyncio.create_task(st_engine_task())
  await asyncio.Future()

def start_raw_websocket_server():
  asyncio.run(run_ws_server())

if __name__ == '__main__':
  threading.Thread(target=start_raw_websocket_server, daemon=True).start()
  print("=" * 60)
  print("  Smart Home Router SCS v1.0 [MODE MURNI HARDWARE RIIL]")
  print("  Web Dashboard: http://192.168.88.254:5000")
  print("=" * 60)
  socketio.run(app, host='192.168.88.254', port=5000, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)