#!/usr/bin/env bash
# Build the libusb-based J2534 driver for the Tactrix Openport 2.0 on macOS.
# There is no official macOS J2534; the source (dschultzca/j2534) is libusb C,
# so we compile it to driver/libj2534.dylib with clang.
#
#   tools/build_driver_macos.sh
#
# Source is kept in driver/_src for inspection / re-build.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRV="$ROOT/driver"
SRC="$DRV/_src"
mkdir -p "$DRV"

echo "[driver] deps: libusb, pkg-config ..."
command -v brew >/dev/null || { echo "Homebrew нет — https://brew.sh"; exit 1; }
brew list libusb      >/dev/null 2>&1 || brew install libusb
brew list pkg-config  >/dev/null 2>&1 || brew install pkg-config

if [ ! -d "$SRC/.git" ]; then
    echo "[driver] cloning dschultzca/j2534 -> $SRC ..."
    rm -rf "$SRC"
    git clone --depth 1 https://github.com/dschultzca/j2534 "$SRC"
fi

cd "$SRC"
echo "[driver] исходники:"; find . -maxdepth 2 -name '*.c' -o -name '*.cpp' -o -name 'Makefile' -o -name 'CMakeLists.txt' | sed 's,^\./,  ,'

CFLAGS="$(pkg-config --cflags libusb-1.0)"
LIBS="$(pkg-config --libs libusb-1.0)"
SRCS="$(find . -maxdepth 2 -name '*.c' -o -name '*.cpp' | tr '\n' ' ')"

if [ -z "$SRCS" ]; then
    echo "[driver] не нашёл .c/.cpp — пришли вывод 'find $SRC -type f' разработчику"; exit 1
fi

echo "[driver] компилирую clang -> $DRV/libj2534.dylib"
echo "         (исходники: $SRCS)"
clang -dynamiclib -fPIC -O2 \
      -install_name "@rpath/libj2534.dylib" \
      $CFLAGS $SRCS $LIBS -o "$DRV/libj2534.dylib" || {
    echo
    echo "[driver] сборка не прошла. Вероятно в исходниках есть Linux/Windows-специфика."
    echo "Пришли вывод этих двух команд, подправлю под Mac:"
    echo "  find $SRC -type f"
    echo "  clang $CFLAGS $SRCS $LIBS -dynamiclib -o /tmp/x.dylib   # покажет ошибки"
    exit 1
}

echo "[driver] готово: $DRV/libj2534.dylib"
file "$DRV/libj2534.dylib"
echo "Запуск:  MACDIAG_MODE=hw python3 -m uvicorn backend.main:app --port 8000"
