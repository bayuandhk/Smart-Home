#include "fieldflow_ethernet.h"
#include "fieldflow_logger.h"
#include "fieldflow_system_status.h"

#include <WiFi.h>
#include <ETH.h>
#include <SPI.h>

//======================================================
// W5500 SPI PIN (PCB FINAL ESP32-S3)
//======================================================
#define ETH_MISO 13
#define ETH_MOSI 11
#define ETH_SCLK 12
#define ETH_CS   10
#define ETH_INT  -1
#define ETH_RST  -1

//======================================================
// STATIC IP SLAVE
//======================================================
IPAddress local_IP(192,168,88,252);
IPAddress gateway(192,168,88,254);
IPAddress subnet(255,255,255,0);

//======================================================
// INTERNAL STATUS
//======================================================
static bool ethernetConnected = false;

//======================================================
// Ethernet Event Callback
//======================================================
void onEthEvent(arduino_event_id_t event)
{
    switch(event)
    {
        case ARDUINO_EVENT_ETH_START:
        {
            fieldflowLogInfo("ETH START");
            ETH.setHostname("FieldFlowSlave");

            ethernetConnected = false;
            systemStatus.ethernetLink = false;
            break;
        }

        case ARDUINO_EVENT_ETH_CONNECTED:
        {
            fieldflowLogInfo("ETH LINK UP");
            // Tunggu GOT_IP sebelum dianggap READY.
            break;
        }

        case ARDUINO_EVENT_ETH_GOT_IP:
        {
            ethernetConnected = true;

            systemStatus.ethernetLink = true;
            systemStatus.ipAddress = ETH.localIP().toString();

            Serial.print("[INFO ] ETH IP : ");
            Serial.println(systemStatus.ipAddress);

            break;
        }

        case ARDUINO_EVENT_ETH_DISCONNECTED:
        {
            ethernetConnected = false;

            systemStatus.ethernetLink = false;
            systemStatus.tcpConnected = false;

            fieldflowLogWarn("ETH LINK DOWN");
            break;
        }

        case ARDUINO_EVENT_ETH_STOP:
        {
            ethernetConnected = false;

            systemStatus.ethernetLink = false;
            systemStatus.tcpConnected = false;

            fieldflowLogWarn("ETH STOP");
            break;
        }

        default:
            break;
    }
}

//======================================================
// Ethernet Initialization
//======================================================
void fieldflowEthernetBegin()
{
    fieldflowLogInfo("Init Ethernet");

    WiFi.onEvent(onEthEvent);

    // SPI BUS SESUAI PCB FINAL
    SPI.begin(ETH_SCLK, ETH_MISO, ETH_MOSI, ETH_CS);

    ETH.begin(
        ETH_PHY_W5500,
        1,          // PHY Address
        ETH_CS,
        ETH_INT,
        ETH_RST,
        SPI         // Gunakan SPI yang sudah diinisialisasi
    );

    // Static IP
    ETH.config(local_IP, gateway, subnet);
}

//======================================================
// Periodic Ethernet Task
//======================================================
void fieldflowEthernetLoop()
{
    // Belum ada task periodik.
}

//======================================================
// Ethernet Ready Checker
// Dipakai TCP Bus dan OLED
//======================================================
bool ethernetReady()
{
    return ethernetConnected &&
           ETH.linkUp() &&
           ETH.localIP() != IPAddress(0,0,0,0);
}
//======================================================
// GET CURRENT IP ADDRESS
//======================================================
IPAddress fieldflowEthernetIP()
{
    return ETH.localIP();
}