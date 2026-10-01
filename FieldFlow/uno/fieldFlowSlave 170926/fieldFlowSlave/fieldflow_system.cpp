#include "fieldflow_system.h"
#include "fieldflow_logger.h"
#include "fieldflow_ethernet.h"
#include "fieldflow_tcp_bus.h"
#include "fieldflow_manifest.h"
#include "fieldflow_registry.h"
#include "fieldflow_scheduler.h"
#include "fieldflow_display.h"
#include "fieldflow_system_status.h"

#include <Arduino.h>

void fieldflowSystemBegin()
{
    Serial.begin(115200);
    delay(2000);

    Serial.println();
    Serial.println("============================");
    Serial.println("FIELD FLOW SLAVE CONTROLLER");
    Serial.println("============================");

    fieldflowLogInfo("System boot");

    fieldflowEthernetBegin();
    fieldflowTcpBusBegin();
    fieldflowManifestBegin();
    fieldflowRegistryBegin();
    fieldflowSchedulerBegin();
    fieldflowSystemStatusBegin();
    fieldflowDisplayBegin();
}

void fieldflowSystemLoop()
{
    fieldflowEthernetLoop();
    fieldflowTcpBusLoop();
    fieldflowSchedulerLoop();
}