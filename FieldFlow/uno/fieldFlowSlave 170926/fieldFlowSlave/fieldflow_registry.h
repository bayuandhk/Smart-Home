#ifndef FIELDFLOW_REGISTRY_H
#define FIELDFLOW_REGISTRY_H

#include <Arduino.h>
#include "fieldflow_driver_base.h"

#define FIELD_FLOW_MAX_INSTANCE 8

uint8_t fieldflowResolvePort(const String& port);
struct SensorInstance
{
    bool active;

    String instanceId;
    String sensorType;
    String port;

    uint32_t sampleMs;
    uint32_t lastTick;

    uint8_t pin;

    FieldFlowDriverBase* driver;
};

void fieldflowRegistryBegin();

void fieldflowRegistryClear();

bool fieldflowRegistryAdd(const String& instanceId,
                          const String& sensorType,
                          const String& port,
                          uint32_t sampleMs);

uint8_t fieldflowRegistryCount();

const SensorInstance* fieldflowRegistryGet(uint8_t index);

SensorInstance* fieldflowRegistryGetMutable(uint8_t index);

bool fieldflowRegistryAttachDriver(uint8_t index,
                                  FieldFlowDriverBase* driver,
                                  uint8_t pin);

void fieldflowRegistryPrint();

#endif