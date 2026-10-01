#ifndef FIELDFLOW_TCP_BUS_H
#define FIELDFLOW_TCP_BUS_H

#include <Arduino.h>

void fieldflowTcpBusBegin();
void fieldflowTcpBusLoop();

bool tcpBusConnected();

bool fieldflowTcpPublish(const String& json);

#endif