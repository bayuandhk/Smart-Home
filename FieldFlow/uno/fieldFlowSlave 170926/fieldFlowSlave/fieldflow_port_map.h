#ifndef FIELDFLOW_PORT_MAP_H
#define FIELDFLOW_PORT_MAP_H

#include <Arduino.h>

uint8_t fieldflowResolvePort(const String &port);
bool fieldflowIsValidGPIO(uint8_t gpio);

#endif