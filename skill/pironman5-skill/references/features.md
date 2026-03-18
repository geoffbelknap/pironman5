# Pironman 5 (Standard) Hardware Snapshot

## Quick facts
- **Target board:** Raspberry Pi 5 only (all RAM bins).
- **Chassis:** Silver anodized aluminum body with two clear acrylic side panels.
- **Overall size:** 111.9 × 78.5 × 117 mm.
- **Power:** USB-C 5 V/5 A input (27 W PSU strongly recommended to avoid brownouts).
- **Cooling stack:** Tower cooler with a PWM 40×40×10 mm fan + two RGB chassis fans tied to the WS2812 bus.
- **Lighting:** 4 onboard WS2812-5050 addressable LEDs plus the two RGB fans (total 6 controllable endpoints by default).
- **Display:** Integrated 0.96" 128×64 OLED (tap-to-wake through vibration sensor) showing CPU, RAM, temp, IP, etc.
- **Controls & IO:**
  - Metal power button wired for safe shutdown.
  - 38 kHz IR receiver.
  - External labeled GPIO extender + spring-loaded microSD slot.
  - Dual full-size HDMI, 2×USB2, 2×USB3, GbE, USB-C power.
- **Storage expansion:** Single PCIe 2.0 M.2 M-key slot supporting 2230/2242/2260/2280 NVMe SSDs or Hailo-8L (w/ adapter).
- **Other:** Onboard RTC backed by a CR1220 cell.

## Thermal + airflow notes
- Tower cooler exhausts upward; keep at least 40 mm of headroom above case.
- The two RGB fans mount on the sides; their RPM is PWM-controlled through the `pironman5` daemon.
- When OpenClaw needs a silent profile, drop `rgb_brightness` below 30 and set mode to `solid`.

## Display + lighting behavior
- OLED sleeps after the configured timeout; `pironman5 -os 0` keeps it awake.
- RGB effects are disabled whenever `rgb_enable` is `false` (common after firmware resets).
- Default LED order is stored in `rgb_position`; keep count at 18 if you chain extra LEDs (6 onboard + 12 fan segments).

## When to prefer this case over Mini/Max
- You need the OLED but only one NVMe slot.
- You prefer the slimmer width (saves ~10 mm compared to Pironman 5 Max).
- Workloads sit between "desk-friendly" and "always-on" NAS: less bulky than Max, more feature-rich than Mini.
