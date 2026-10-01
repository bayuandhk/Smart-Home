import json
import asyncio
from edge_server.config import get_slaves_config

class SlaveManager:
    def __init__(self):
        self.slaves = {} # slave_id atau uid -> session info
        self.config = get_slaves_config()

    def register_slave(self, slave_uid, slave_id, writer):
        self.slaves[slave_uid] = {
            "slave_id": slave_id,
            "writer": writer,
            "status": "online"
        }
        print(f"[SlaveManager] Slave terdaftar: {slave_uid} (ID: {slave_id})")

    def get_slave(self, slave_uid):
        return self.slaves.get(slave_uid)

    def remove_slave(self, slave_uid):
        if slave_uid in self.slaves:
            del self.slaves[slave_uid]
            print(f"[SlaveManager] Slave terputus: {slave_uid}")

    async def send_to_slave(self, slave_uid, message: dict):
        slave = self.slaves.get(slave_uid)
        if slave and slave['writer']:
            try:
                data = json.dumps(message)
                # ESP32 usually reads until newline or expects a raw string
                slave['writer'].write((data + "\n").encode('utf-8'))
                await slave['writer'].drain()
                print(f"[SlaveManager] 📤 Terkirim ke {slave_uid}: {data}")
                return True
            except Exception as e:
                print(f"[SlaveManager] ❌ Error mengirim ke {slave_uid}: {e}")
                self.remove_slave(slave_uid)
        else:
            print(f"[SlaveManager] ⚠️ Gagal kirim ke {slave_uid}: Slave tidak terhubung (Daftar slave online: {list(self.slaves.keys())})")
        return False


    async def broadcast(self, message: dict):
        for uid in list(self.slaves.keys()):
            await self.send_to_slave(uid, message)

slave_manager = SlaveManager()
