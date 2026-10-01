#pragma once

#include <Arduino.h>

// Runtime debug flag
extern bool fieldflowDebugEnable;

// Runtime debug control
void fieldflowSetDebug(bool enable);
bool fieldflowDebugEnabled();

// Logger
void fieldflowLogInfo(const char *msg);
void fieldflowLogWarn(const char *msg);
void fieldflowLogError(const char *msg);
void fieldflowLogDebug(const String &msg);