#ifndef FIELDFLOW_SYSTEM_STATUS_H
#define FIELDFLOW_SYSTEM_STATUS_H

#include <Arduino.h>

struct FieldFlowSystemStatus
{
    uint8_t slaveId = 1;
    uint16_t manifestVersion = 0; 
    bool ethernetLink = false;
    bool tcpConnected = false;
    bool manifestLoaded = false;

    uint8_t sensorCount = 0;
    uint8_t relayCount = 0;
    
    uint32_t freeHeap = 0;
    uint32_t minHeap = 0;
    uint32_t uptimeSec = 0;

    uint32_t tcpRxCounter = 0;
    uint32_t tcpTxCounter = 0;
    uint32_t heartbeatCounter = 0;
    uint32_t etlCounter = 0;
    uint32_t tcpReconnectCounter = 0;

    uint32_t lastHeartbeatMillis = 0;
    uint32_t lastETLMillis = 0;

    String ipAddress = "";
};

extern FieldFlowSystemStatus systemStatus;

void fieldflowSystemStatusBegin();
void fieldflowSystemStatusLoop();

#endif