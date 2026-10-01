#include "fieldflow_tcp_bus.h"
#include "fieldflow_logger.h"
#include "fieldflow_ethernet.h"
#include "fieldflow_manifest.h"
#include "fieldflow_system_status.h"

#include <WiFi.h>

//======================================================
// TCP CLIENT (Slave -> Main Controller)
//======================================================

static IPAddress serverIP(192,168,88,253);
static const uint16_t serverPort = 5000;

static WiFiClient client;

static bool helloSent = false;
static unsigned long lastReconnectAttempt = 0;
static unsigned long lastHeartbeat = 0;

static String rxLine;

//======================================================

static void connectServer()
{
    if(client.connected()) return;

    fieldflowLogInfo("Connecting main panel");

    if(client.connect(serverIP, serverPort))
    {
        client.setNoDelay(true);
        client.setTimeout(20);

        helloSent = false;
        rxLine = "";

        systemStatus.tcpConnected = true;
        systemStatus.tcpReconnectCounter++;

        fieldflowLogInfo("TCP connected");
    }
    else
    {
        systemStatus.tcpConnected = false;
        fieldflowLogWarn("TCP connect failed");
    }
}

//======================================================

static void sendHello()
{
    if(!client.connected()) return;
    if(helloSent) return;

    client.println(
        "{\"type\":\"hello\"," 
        "\"slave_id\":1," 
        "\"slave_uid\":\"SLV-01\"," 
        "\"device_type\":\"slave_sensor\"," 
        "\"fw\":\"2.1.0\"}"
    );

    client.flush();

    helloSent = true;

    systemStatus.tcpTxCounter++;

    fieldflowLogInfo("HELLO sent");
}

//======================================================

static void sendHeartbeat()
{
    if(!client.connected()) return;

    client.println("{\"type\":\"heartbeat\",\"slave_id\":1}");
    client.flush();

    systemStatus.heartbeatCounter++;
    systemStatus.tcpTxCounter++;
    systemStatus.lastHeartbeatMillis = millis();

    if(fieldflowDebugEnabled())
        fieldflowLogDebug("Heartbeat sent");
}

//======================================================

void fieldflowTcpBusBegin()
{
    rxLine.reserve(4096);
    fieldflowLogInfo("TCP bus init");
}

//======================================================

void fieldflowTcpBusLoop()
{
    if(!ethernetReady())
    {
        if(client.connected())
            client.stop();

        helloSent = false;
        systemStatus.tcpConnected = false;
        return;
    }

    if(!client.connected())
    {
        helloSent = false;

        if(millis() - lastReconnectAttempt >= 3000)
        {
            lastReconnectAttempt = millis();
            connectServer();
        }

        return;
    }

    sendHello();

    while(client.available())
    {
        char c = client.read();

        if(c == '\n')
        {
            rxLine.trim();

            if(rxLine.length())
            {
                systemStatus.tcpRxCounter++;
                fieldflowManifestHandle(rxLine);
            }

            rxLine = "";
        }
        else if(c != '\r')
        {
            if(rxLine.length() < 4096)
                rxLine += c;
        }
    }

    if(millis() - lastHeartbeat >= 5000)
    {
        lastHeartbeat = millis();
        sendHeartbeat();
    }
}

//======================================================

bool tcpBusConnected()
{
    return client.connected();
}

//======================================================

bool fieldflowTcpPublish(const String &json)
{
    if(!client.connected())
        return false;

    size_t sent = client.println(json);

    if(sent == 0)
    {
        fieldflowLogWarn("TCP TX failed");

        client.stop();
        helloSent = false;
        systemStatus.tcpConnected = false;

        return false;
    }

    client.flush();

    systemStatus.tcpTxCounter++;

    return true;
}