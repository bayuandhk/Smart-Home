#include "fieldflow_system_status.h"

FieldFlowSystemStatus systemStatus;

void fieldflowSystemStatusBegin()
{
    systemStatus.freeHeap = ESP.getFreeHeap();
    systemStatus.minHeap  = ESP.getMinFreeHeap();
}

void fieldflowSystemStatusLoop()
{
    systemStatus.freeHeap = ESP.getFreeHeap();
    systemStatus.minHeap  = ESP.getMinFreeHeap();
    systemStatus.uptimeSec = millis()/1000;
}