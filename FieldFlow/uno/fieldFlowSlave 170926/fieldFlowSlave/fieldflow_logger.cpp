#include "fieldflow_logger.h"

bool fieldflowDebugEnable = false;

void fieldflowSetDebug(bool enable)
{
    fieldflowDebugEnable = enable;
}

bool fieldflowDebugEnabled()
{
    return fieldflowDebugEnable;
}

void fieldflowLogInfo(const char *msg)
{
    Serial.print("[INFO ] ");
    Serial.println(msg);
}

void fieldflowLogWarn(const char *msg)
{
    Serial.print("[WARN ] ");
    Serial.println(msg);
}

void fieldflowLogError(const char *msg)
{
    Serial.print("[ERROR] ");
    Serial.println(msg);
}

void fieldflowLogDebug(const String &msg)
{
    if(fieldflowDebugEnable)
    {
        Serial.print("[DEBUG] ");
        Serial.println(msg);
    }
}