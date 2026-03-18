# Pironman 5 (Standard) – Working Notes

## 1. Bring-up checklist
1. Update Pi firmware + EEPROM (`sudo rpi-eeprom-update -a`).
2. Confirm `libcamera` stack works before sealing the case if you rely on the FFC camera.
3. Install Pironman service bundle (`sudo pip install pironman5` or vendor script) before enabling OpenClaw agents.
4. Provision a 27 W USB-C supply; undervoltage instantly blanks the OLED and RGB.

## 2. Service health + logging
```bash
systemctl status pironman5.service
journalctl -u pironman5.service -n 120 --no-pager
sudo tail -f /var/log/pironman5/pm_auto.*.log
```
- Restart after every CLI config change: `sudo systemctl restart pironman5.service`.
- If OLED stays blank, also restart `systemd-udevd` or reboot; vibration wake depends on GPIO interrupts.

## 3. CLI snippets (standard case defaults)
| Task | Command |
| --- | --- |
| Show config | `pironman5 -c` |
| Enable RGB | `sudo pironman5 -re true` |
| Set solid color | `sudo pironman5 -rs solid && sudo pironman5 -rc ff6b00` |
| Adjust brightness (0–100) | `sudo pironman5 -rb 35` |
| Switch breathing/rainbow | `sudo pironman5 -rs breathing` (solid returns control to manual colors) |
| OLED power | `sudo pironman5 -oe true/false` |
| OLED rotation | `sudo pironman5 -or 0` (upright) or `180` |
| OLED pages | `sudo pironman5 -op mix,performance,ips,disk` |
| OLED sleep timeout | `sudo pironman5 -os 120` (seconds, 0 = never sleep) |
| Dashboard launch (local desktop) | `pironman5 launch-browser` then open `http://localhost:34001` |

## 4. Storage & PCIe lane usage
1. Shut down (`sudo poweroff`), install NVMe, secure the standoff that matches drive length.
2. After boot, verify link with `ls /dev/nvme*` and `sudo smartctl -a /dev/nvme0`.
3. Format for NAS workloads via `sudo mkfs.ext4 /dev/nvme0n1` (or ZFS/Btrfs pools) before attaching to Samba/NFS services.
4. When pairing with Hailo-8L, use an M-key Hailo adapter and disable autosuspend for the PCIe root complex.

## 5. Optional modules
- **Camera bay:** route the 15-pin FFC along the tower cooler wall; keep it away from the fan blades.
- **3.5" SPI screen:** use the right-side acrylic panel standoffs and feed the ribbon through the GPIO extender slot.
- **RTL-SDR:** plug into USB3, then run `sudo nano /boot/firmware/config.txt` to comment out `dtoverlay=vc4-kms-v3d` only if SDR stack requires legacy video.

## 6. Integrating with OpenClaw automations
1. Ensure OpenClaw agent user belongs to the `gpio`, `i2c`, and `dialout` groups if you trigger CLI calls via scripts.
2. Wrap long-running LED/OLED routines in shell helpers under `~/bin` and invoke them from tasks to avoid repeating privileged commands.
3. Track config drift: `sudo git init /opt/pironman5 && sudo git status` is handy before editing vendor Python files.

## 7. Troubleshooting quick hits
- **All LEDs off:** `pironman5 -c` shows `"rgb_enable": false` → re-enable + restart.
- **OLED frozen:** run `sudo i2cdetect -y 1` to ensure address `0x3C` exists; reseat ribbon if missing.
- **Fans loud:** drop brightness and set `pironman5 -rs solid`, then cap fan PWM via `pi-fan-curve` inside the dashboard.
