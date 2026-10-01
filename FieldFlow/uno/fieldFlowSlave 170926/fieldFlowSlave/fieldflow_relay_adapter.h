#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

#define MAX_RUNTIME_RELAYS 32

struct RelayRuntime
{
    String instanceId;
    String title;

    uint8_t gpio;
    uint8_t channel;
    bool activeHigh;

    bool state;
    bool enabled;
};

extern RelayRuntime relayRegistry[MAX_RUNTIME_RELAYS];
extern uint8_t relayCount;

// Runtime Manifest
void relayRuntimeClear();
void relayRuntimeLoad(JsonArray actuatorArray);

bool relayRuntimeSetChannel(uint8_t channel, bool value);
// Runtime Command
bool relayRuntimeExecute(const String &instanceId, bool value);

// Runtime Lookup
int relayRuntimeFind(const String &instanceId);

// Runtime ACK
String relayRuntimeCreateAck(const String &instanceId);