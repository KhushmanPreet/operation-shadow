# Operation Shadow — Onboard Vehicle & Embedded Hardware (`hardware/`)

Isolated onboard companion-computer and microcontroller firmware tier for **Operation Shadow**:

- `scout/` — **SCOUT01** ground rover Raspberry Pi stack (waypoint navigation, reactive obstacle avoidance, sensor fusion, ESP32 UART serial bridge, and authenticated WebSocket client).
- `hawk/` — **HAWK01** indoor aerial drone companion stack (flight controller interface, onboard geofence enforcement, altitude/battery telemetry monitor, and camera stream).
- `firmware/esp32/` — **ESP32** low-level C++ firmware (`main.cpp`) for PWM motor control, ultrasonic/ToF/temperature/gas ADC reading, and hardware kill-switch watchdog.
