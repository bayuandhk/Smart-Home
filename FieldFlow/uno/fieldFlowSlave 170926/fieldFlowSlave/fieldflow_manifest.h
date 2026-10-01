#ifndef FIELDFLOW_MANIFEST_H
#define FIELDFLOW_MANIFEST_H

#include <Arduino.h>

void fieldflowManifestBegin();
void fieldflowManifestHandle(const String& json);

#endif