import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLAVES_CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'slaves.json')

TCP_HOST = '0.0.0.0'
TCP_PORT = 5000

# Untuk WS server jika dibutuhkan
WS_HOST = '0.0.0.0'
WS_PORT = 8765

def get_slaves_config():
    if os.path.exists(SLAVES_CONFIG_PATH):
        with open(SLAVES_CONFIG_PATH, 'r') as f:
            data = json.load(f)
            return data.get("slaves", [])
    return []
