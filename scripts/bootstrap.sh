#!/usr/bin/env bash
set -e

OS=$(uname -s)

if [ "$OS" = "Darwin" ]; then
    echo "Bootstrapping macOS dependencies..."

    # Ensure Homebrew exists
    if ! command -v brew >/dev/null 2>&1; then
        echo "Homebrew not found! Install it first: https://brew.sh"
        exit 1
    fi

    brew update

    # INDI deps
    brew tap indilib/indi || true
    brew install indi dbus glib jpeg cmake pkg-config swig

    # Optional: export paths (if using a shell that doesn't auto-source brew env)
    export PKG_CONFIG_PATH="/opt/homebrew/opt/dbus/lib/pkgconfig:/opt/homebrew/opt/glib/lib/pkgconfig:$PKG_CONFIG_PATH"
    export CFLAGS="-I/opt/homebrew/include -I/opt/homebrew/include/libindi $CFLAGS"
    export LDFLAGS="-L/opt/homebrew/lib $LDFLAGS"
fi

if [ "$OS" = "Linux" ]; then
    echo "Bootstrapping Linux dependencies..."
    sudo apt-get update
    sudo apt-get install -y \
        cmake \
        libdbus-1-dev \
        libglib2.0-dev \
        libjpeg-dev \
        libindi-dev \
        swig \
        pkg-config
fi

echo "Installing Python deps…"
pip install --upgrade pip
pip install ".[dev]"
