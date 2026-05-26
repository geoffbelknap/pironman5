#!/bin/bash

set -euo pipefail
trap 'echo "Error occurred. Exiting..." >&2; exit 1' ERR

echo "Checking system and fixing GPIO/SPI permissions..."

# Check if the system is Kali Linux
if ! grep -q "Kali" /etc/os-release; then
    echo "This is not a Kali Linux system, no changes made"
    exit 0
fi

echo "Detected Kali Linux system"

# Check if user is root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit 1
fi

echo "Fixing GPIO and SPI permissions..."

# Function to find an available system GID (less than 1000)
find_available_system_gid() {
    for ((gid=999; gid>=100; gid--)); do
        if ! getent group "$gid" > /dev/null; then
            echo "$gid"
            return
        fi
    done
    echo "0"  # Return 0 if no available GID found
}

# Function to fix group to be a system group
fix_group_to_system() {
    local group_name="$1"
    
    if ! getent group "$group_name" > /dev/null; then
        echo "Creating $group_name system group"
        groupadd -r "$group_name"
    else
        echo "$group_name group already exists, checking if it's a system group"
        # Check if it's a system group (GID < 1000)
        local group_gid=$(getent group "$group_name" | cut -d: -f3)
        if [ "$group_gid" -ge 1000 ]; then
            echo "Converting $group_name group to system group"
            # Find available system GID
            local available_gid=$(find_available_system_gid)
            if [ "$available_gid" != "0" ]; then
                echo "Changing $group_name group GID to $available_gid"
                groupmod -g "$available_gid" "$group_name"
            else
                echo "No available system GID found for $group_name group"
            fi
        else
            echo "$group_name group is already a system group"
        fi
    fi
}

# Fix GPIO group
fix_group_to_system "gpio"

# Fix SPI group
fix_group_to_system "spi"

echo "GPIO and SPI permissions fixed successfully!"