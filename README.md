# NYC Daycare Commute Finder 🗽🎒

An interactive, commuter-focused daycare discovery tool for New York City, rebuilt entirely in Rust & WebAssembly.

## 🚀 Quick Start (Running the App)

The backend data is pre-compiled using a Python build script, and the application runs entirely in the browser using WebAssembly.

### Prerequisites:
- `cargo` and `rustup` installed.
- `trunk` installed (`cargo install trunk`).
- `uv` or Python 3.12+ for the data build step.

### 1. Build Data Files
```bash
uv run build_data.py
```
*This downloads the subway stations, daycare inspections, and walking network, placing them in `public/data/`.*

### 2. Start the Application
```bash
trunk serve
```
*This compiles the Rust application to WebAssembly and hosts it on a local dev server at `http://127.0.0.1:8080/`.*
