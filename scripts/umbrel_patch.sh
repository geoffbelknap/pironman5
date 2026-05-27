# If not umbrel os, skip
if ! [ -d "/home/umbrel/umbrel" ]; then
    echo "Not Umbrel OS, skip remount /boot."
    exit 0
fi

# Remount /boot if it's read-only
if findmnt -n -o OPTIONS /boot | grep -q "ro"; then
    echo "Remount /boot as read-write..."
    mount -o remount,rw /boot
else
    echo "/boot is already mounted as read-write."
fi

# Create GPIO group if not exists
if ! getent group gpio > /dev/null; then
    echo "Creating gpio group"
    groupadd -r gpio
fi
# create spi group if not exists
if ! getent group spi > /dev/null; then
    echo "Creating spi group"
    groupadd -r spi
fi
# Set gpio and spi group ownership
chown :gpio /dev/gpiochip*
echo "Set gpio group ownership to gpio"
chown :spi /dev/spidev*
echo "Set spi group ownership to spi"

# cp udev rule to /etc/udev/rules.d/
cp ./pironman5/assets/bin/99-com.rules /etc/udev/rules.d/
# reload udev rules
udevadm control --reload-rules
echo "udev rules reloaded."
