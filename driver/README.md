# J2534 driver

The Openport 2.0 J2534 driver goes here (gitignored — it's a built binary):

- **macOS:** `libj2534.dylib` — build with `tools/build_driver_macos.sh`
- **Linux:** `libj2534.so`
- **Windows:** uses the installed Tactrix `op20pt32.dll` (no need to place here)

The backend auto-detects `./driver/libj2534.*` and common system paths, or set
`MACDIAG_DRIVER=/full/path`. Run with `MACDIAG_MODE=hw`.
