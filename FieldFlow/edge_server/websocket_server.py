from edge_server.router import router

class WebSocketServerBridge:
    """
    Menjembatani antara HMI (Socket.IO di app.py) dan Router (Edge Server).
    HMI tidak berbicara langsung ke Slave, tapi lewat sini.
    """
    def __init__(self):
        router.set_ws_server(self)
        self.app_module = None

    def set_app_module(self, app_module):
        self.app_module = app_module

    async def forward_etl_to_hmi(self, slave_uid, message):
        """
        Diterima dari Router (data sensor/heartbeat), update UI.
        """
        if self.app_module:
            # Karena dipanggil dari event loop asyncio, kita jalankan fungsi update state HMI
            self.app_module.process_inbound_from_edge(slave_uid, message)

ws_bridge = WebSocketServerBridge()
