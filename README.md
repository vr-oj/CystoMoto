# CystoMoto

Live pressure and mass data logger for cystometry experiments. Connects to an Arduino-controlled pressure transducer, displays real-time traces, controls a syringe pump, and saves synchronized CSV files.

---

## How to Use

### 1. Connect the Device
- Select the Arduino serial port from the dropdown in the toolbar.
- Or select **Virtual CystoMoto (Built-in simulator)** to test plotting without hardware.
- Click **Connect CystoMoto Device**.
- The status panel will show "Connected" when the device is recognized.

### 2. Zero the Pressure
- Before starting an experiment, make sure there is no pressure applied.
- Click **Zero Device?** to baseline the sensor.

### 3. Record Data
- Click **⏺ Start Recording** to create a new file and open the run setup dialog. Choose the CSV destination for this run and enter any experiment metadata you want saved with it.
- CystoMoto saves the live data to the selected CSV and writes the run metadata to a companion `*_metadata.json` file in the same folder.
- Click **Start Fill** to start the syringe pump. A green marker appears on the plot.
- Click **Stop Pump** to stop the pump. A red marker appears. Recording continues.
- Click **⏹ Stop Recording** to finalize and close the CSV file.

Each recording is saved to a timestamped folder under `~/Documents/CystoMoto Results/YYYY-MM-DD/FillN/`.

The CSV includes one row per sample: `Frame Index`, `Time (s)`, `Pressure (mmHg)`, `Mass (g)`, `Pump Running` (0 or 1), `Pump Event`, and `Marker Time (s)`. If multiple pump events occur between samples, they are joined with semicolons in the event/time columns instead of creating extra rows.

### 4. Plot Controls
- **Auto-scale X**: fit the full trace on the time axis. Turn it off to use the trailing live window or manual X limits.
- **Auto-scale Pressure Y / Mass Y**: toggle automatic vertical scaling.
- **Reset Zoom/View**: restore the default view.
- **Clear Plot Data**: wipe the live traces (does not affect the saved CSV).
- **Export Plot Image**: save the current plot as an image file.
- **Side by Side / Stacked**: toggle between vertical and horizontal plot layout.

### 5. Export
- **File → Export Plot Data (CSV)**: export all currently plotted data as a CSV.
- **File → Export Plot Image**: save the plot as an image.
- **File → Set Results Folder**: change the default save location.

---

## Install from a Release (No coding required)

Download the latest release for your platform from the [Releases page](../../releases).

### macOS
1. Download `CystoMoto_<version>_macOS_<arch>.dmg`.
2. Open the `.dmg` file.
3. Drag **CystoMoto.app** into your Applications folder.
4. Launch CystoMoto from Applications.

> If macOS blocks the app ("unidentified developer"), right-click the app and choose **Open**, then confirm.

### Windows
1. Download `CystoMoto_Setup_v<version>.exe`.
2. Run the installer and follow the prompts.
3. Launch CystoMoto from the Start menu or desktop shortcut.

---

## Building a macOS Release Manually (for Intel Macs)

The automated CI only builds for Apple Silicon (arm64). To include an Intel macOS DMG in a release, build it manually on an Intel Mac and upload it alongside the CI-generated artifacts.

**Requirements:** Python 3.10+, Homebrew

```bash
# 1. Install build tools
pip install pyinstaller pillow
pip install -r cysto_app/requirements.txt
brew install create-dmg

# 2. Patch the version number (replace 1.0.0 with the release version)
VERSION="1.0.0"
sed -i '' "s/APP_VERSION = \"[^\"]*\"/APP_VERSION = \"$VERSION\"/" cysto_app/utils/config.py
sed -i '' "s/APP_VERSION=\"[^\"]*\"/APP_VERSION=\"$VERSION\"/" build_macos.sh
sed -i '' "s/version=\"[^\"]*\"/version=\"$VERSION\"/" CystoMoto_macos.spec
sed -i '' "s/\"CFBundleVersion\": \"[^\"]*\"/\"CFBundleVersion\": \"$VERSION\"/" CystoMoto_macos.spec
sed -i '' "s/\"CFBundleShortVersionString\": \"[^\"]*\"/\"CFBundleShortVersionString\": \"$VERSION\"/" CystoMoto_macos.spec

# 3. Build
chmod +x build_macos.sh
./build_macos.sh
```

This produces `installer_output/CystoMoto_<version>_macOS_x86_64.dmg`.

**Upload to the release:**
1. Go to the repo → **Releases** → open the draft release for this version.
2. Drag and drop the `.dmg` into the assets area.
3. Publish the release.

> To verify your architecture before building, run `uname -m`. It should print `x86_64` for Intel.

---

## Install from Source

### Requirements
- Python 3.10 or newer
- pip

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/valdovegarodr/CystoMoto.git
cd CystoMoto

# 2. Create and activate a virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

# 3. Install dependencies
pip install -r cysto_app/requirements.txt

# 4. Run the app
python cysto_app/cysto_app.py

# Optional: run with Qt preflight first
make run
```

---

## Arduino Firmware

The app expects serial data at **115200 baud** in this format:

```
frame_index,elapsed_time_s,pressure_mmhg[,mass_g]
```

The `mass_g` field is optional — if omitted, mass is recorded as `0.0`.

If you do not have hardware connected, choose **Virtual CystoMoto** in the device list. The built-in simulator emits realistic pressure and mass data continuously and responds to the same `Z`, `G`, and `S` commands used by the Arduino workflow.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No serial ports listed | Check USB connection and install Arduino drivers |
| App shows "Serial Error" | Verify the correct port is selected and the baud rate is 115200 |
| macOS blocks the app | Right-click → Open → confirm launch |
| Plot shows no data | Check that the Arduino is streaming (Console Log in View menu) |
| Qt startup fails (`cocoa` plugin / platform plugin errors) | Run `make check-qt` then `make qt-repair` |

---

## License

[Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-nc-sa/4.0/)
