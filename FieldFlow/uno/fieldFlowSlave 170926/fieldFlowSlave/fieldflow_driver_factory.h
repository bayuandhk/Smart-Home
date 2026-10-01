#ifndef FIELDFLOW_DRIVER_FACTORY_H
#define FIELDFLOW_DRIVER_FACTORY_H

#include <Arduino.h>
#include "fieldflow_driver_base.h"

FieldFlowDriverBase* fieldflowCreateDriver(
    const String& sensorType,
    uint8_t pin
);

uint8_t fieldflowResolvePort(const String &port);

#endif