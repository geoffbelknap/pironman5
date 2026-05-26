#!/bin/bash

set -euo pipefail
trap 'echo "Error occurred. Exiting..." >&2; exit 1' ERR

echo "=== LGPIO Installation Script (Universal Compatibility) ==="

# 1. Check for root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Error: Please run as root (use sudo)"
  exit 1
fi

# 2. Install via package manager. The old source fallback downloaded lgpio over
# HTTP and built it as root; hardened installs fail closed instead.
echo "- Attempting to install via apt..."
if DEBIAN_FRONTEND=noninteractive apt-get install -y liblgpio-dev python3-lgpio 2>/dev/null; then
    echo "✓ LGPIO installed successfully via apt."
    exit 0
else
    echo "Error: apt package liblgpio-dev/python3-lgpio not found. Refusing unauthenticated source fallback." >&2
    exit 1
fi
