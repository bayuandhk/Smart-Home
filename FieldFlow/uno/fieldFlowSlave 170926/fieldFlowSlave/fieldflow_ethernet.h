#ifndef FIELDFLOW_ETHERNET_H
#define FIELDFLOW_ETHERNET_H

#include <Arduino.h>
#include <IPAddress.h>

// Inisialisasi Ethernet W5500
void fieldflowEthernetBegin();

// Task periodik Ethernet (dipanggil setiap loop sistem)
void fieldflowEthernetLoop();

// Status Ethernet
bool ethernetReady();

// IP Address aktif Ethernet
IPAddress fieldflowEthernetIP();

#endif