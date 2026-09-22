#!/bin/bash
# SafeEject macOS Installer (Delegates to project root installer)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "$DIR/install.sh"
