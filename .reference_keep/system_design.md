# ESP-NOW Sensor Network -- System Design

## Overview

This system creates a scalable sensor/actuator network using ESP32
devices communicating via ESP‑NOW. A USB gateway connects the network to
a server such as Home Assistant.

Main goals:

-   No WiFi infrastructure required in the field
-   Long distance communication (\~160 m)
-   OTA firmware updates
-   Auto‑configuration of sensors
-   Multi‑hop routing (relay nodes)
-   Integration with Home Assistant via MQTT

## Network Architecture

Server (Home Assistant) │ │ USB │ ESP32‑S3 Gateway │ ESP‑NOW │ Multi‑hop
mesh │ ESP32 Nodes (sensor / relay)

## Node Types

Sensor node - reads sensors - may enter deep sleep

Relay node - forwards packets - always powered

Gateway node - connected by USB - publishes MQTT

## Typical Hardware

Short range nodes ESP32‑C3 SuperMini

Long range nodes ESP32 DevKit with external antenna

Gateway ESP32‑S3 with USB + optional display

## Radio Planning

Environment: vegetation and hills.

Recommended:

-   antenna height \> 1.5 m
-   3‑5 dBi antenna for relay nodes
-   PCB antenna acceptable for short links

Typical ranges:

Indoor: 30‑50 m Urban: 80‑120 m Open field: 200‑300 m Vegetation:
100‑180 m

## Packet Structure

Binary packet example:

struct espnow_packet { uint8_t version; uint8_t type; uint8_t src;
uint8_t dst; uint8_t ttl; uint8_t flags; uint32_t seq; uint32_t
timestamp; int16_t value1; int16_t value2; uint8_t sensor_type; uint16_t
crc; };

## Packet Types

0 HELLO\
1 SENSOR\
2 HEARTBEAT\
3 COMMAND\
4 OTA\
5 ACK

## Mesh Routing

Each node maintains neighbor table:

node_id\
RSSI\
hop_to_gateway

Route score:

score = RSSI − (hop × 10)

Highest score selected.

## Sensor Auto‑Configuration

Nodes can detect sensors automatically.

Examples:

I2C scan

0x44 → SHT31\
0x76 → BME280\
0x23 → BH1750

Ultrasonic sensors can be detected by triggering echo measurement.

## Recommended Sensor Timing

Reservoir monitoring:

measurement: 30 s\
transmit: 120 s\
heartbeat: 60 s

## Gateway Diagnostics

Gateway can display:

Nodes online\
RSSI per node\
Packets per minute\
Alarms
