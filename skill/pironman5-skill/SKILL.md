---
name: pironman5-standard
description: Configure and operate Raspberry Pi 5 builds housed inside the SunFounder Pironman 5 (standard) case. Use this when tasks involve assembling the chassis, validating the pironman5 service, managing cooling/RGB/OLED, provisioning NVMe storage, or controlling the dashboard/CLI on this enclosure.
---

# SunFounder Pironman 5 (Standard Case)

## Quick start
1. Skim `references/features.md` to confirm hardware capabilities (OLED, single NVMe slot, RGB layout, tower cooler).
2. Before touching config, run `systemctl status pironman5.service` and `pironman5 -c` to capture the current state.
3. Apply changes with the CLI (`pironman5 -re/-rc/-rb/-rs/-oe/-op`) or dashboard (`http://<pi-ip>:34001`), then restart the service so OpenClaw-driven automations see the new values.
4. Keep a 27 W USB-C PSU connected—almost every symptom (LEDs off, OLED blank, NVMe drops) comes from undervoltage.

## Core workflows
### 1. Prep + assembly
- Follow the vendor exploded view: install the tower cooler, route camera FFCs before closing the panels, and leave slack near the vibration sensor so the OLED wake tap keeps working.
- Verify GPIO extender orientation; misaligned pins short 5 V rails. `references/workflows.md` lists the bring-up checklist.

### 2. OS + OpenClaw bring-up
- Flash Raspberry Pi OS (64-bit) with PCIe set to Gen 2 in `raspi-config`.
- Install the Pironman daemon before enabling OpenClaw tasks; the agent needs the CLI + dashboard stack already present.
- Add the OpenClaw user to `gpio`, `i2c`, and `dialout` so scripted CLI calls do not fail with permission errors.

### 3. Service control, OLED, and lighting
- Keep a habit: `sudo pironman5 -re true && sudo systemctl restart pironman5.service` any time LEDs mysteriously shut off.
- OLED: `pironman5 -oe true`, adjust rotation (`-or 0/180`), select pages (`-op mix,performance,ips,disk`), and tune sleep timeout (`-os <seconds>`).
- RGB: set style (`-rs solid/breathing/flow/rainbow`), color (`-rc <hex>`), brightness (`-rb 0–100`), and LED count (`-rl <n>` if you chained strips). Solid mode gives manual color control; flow/rainbow override it.

### 4. Storage + expansion
- Power off before installing an NVMe drive. After boot, confirm with `ls /dev/nvme*`, then partition/format.
- For AI accelerators (Hailo-8L), monitor temps via the dashboard—they share the single PCIe lane with the SSD, so schedule workloads accordingly.
- Note that only one PCIe device can sit inside this case at once; use USB 3 enclosures if you need extra drives.

### 5. Optional modules + dashboards
- Optional SPI display, RTL-SDR, or camera modules route through the extender slots—see `references/workflows.md` for wiring notes.
- Dashboard lives at `http://<pi-ip>:34001`; use it for fan curves, OLED page editing, and log review when OpenClaw is offline.

## Diagnostics + recovery
- `journalctl -u pironman5.service -n 200 --no-pager` is the fastest way to see addon failures (RGB, OLED, data logger).
- Logs also sit in `/var/log/pironman5/pm_auto.*.log`; tail the file that matches the component you are debugging.
- If the OLED and LEDs both die, assume power or I2C issues first; reseat the ribbon and reapply power before editing configs.

## References
- [`references/features.md`](references/features.md) — hardware snapshot (dimensions, IO map, lighting/display behavior).
- [`references/workflows.md`](references/workflows.md) — bring-up checklist, CLI table, storage workflow, troubleshooting tips.
