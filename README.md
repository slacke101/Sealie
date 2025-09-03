# Sealie Sense

**Author:** Rafael A Castro  
**Started:** ~March 27, 2025  
**Last Updated:** September 3rd, 2025

---

## Overview

Sealie Sense is a modern, professional Python desktop application for real-time sensor data visualization, device management, and serial communication. Built with Tkinter and ttkbootstrap, it provides a beautiful, responsive UI for monitoring Arduino and other microcontroller sensor data, with advanced features for data logging, export, and analysis.

---

## Features

- **Modern UI:** Dark/light themes, sidebar navigation, topbar quick actions, and professional meters/graphs.
- **Serial Port Management:** Auto-detect, connect/disconnect, baud rate selection, and persistent board naming.
- **Sensor Visualization:**
  - DHT (Temperature/Humidity) and IMU (Yaw, Pitch, Roll) support
  - Real-time meters and time-series graphs
  - 3D orientation visualization for IMU data
- **Data Logging & Export:**
  - Record sensor data to CSV
  - Export all data or current session
- **Settings:**
  - Theme and baud rate selection
  - Board management (rename/remove)
- **AI Data Assistant:**
  - Offline stats, quick plots, and summary via chat
- **Robust Error Handling:**
  - Custom popups for serial errors, connection issues, and troubleshooting tips
- **Extensible:**
  - Easily add new sensor types and visualizations

---

## Installation

### Requirements

- Python 3.10+
- pip
- [ttkbootstrap](https://ttkbootstrap.readthedocs.io/)
- [Pillow](https://python-pillow.org/)
- [pyserial](https://pyserial.readthedocs.io/)
- [matplotlib](https://matplotlib.org/)
- [numpy](https://numpy.org/)
- [pandas](https://pandas.pydata.org/)

### Install dependencies

```bash
pip install ttkbootstrap pillow pyserial matplotlib numpy pandas
```

### (Optional) For AI Assistant:

- [gpt4all](https://github.com/nomic-ai/gpt4all) (offline LLM, optional)

---

## Usage

1. **Connect your Arduino or sensor device** via USB.
2. **Run the app:**
   ```bash
   python main.py
   ```
3. **Select the serial port** from the topbar and click **Connect**.
4. **View live sensor data** on the Dashboard and Sensors tabs.
5. **Add/configure sensors** as needed.
6. **Export data** or start/stop recording from the topbar.
7. **Access settings** for theme, baud rate, and board management.
8. **Use the AI Data Assistant** for quick stats and plots (offline, optional).

---

## Serial Data Format

- DHT: `TEMP:23.5 HUM:45.2` (Fahrenheit, auto-converted to Celsius)
- IMU: `YAW:45.2 PITCH:12.3 ROLL:-5.1` (degrees)
- Generic: `KEY:VALUE ...` (auto-detected)

---

## Troubleshooting

- **Connection Failed:**
  - Check cable and port
  - Try a different baud rate (9600, 115200)
  - Ensure no other app is using the port
  - Use the custom error popup for tips
- **No Data Displayed:**
  - Ensure Arduino is sending data in the correct format
  - Check baud rate matches Arduino code
- **UI Issues:**
  - Use the Settings dialog to switch themes or reset

---

## Customization & Extending

- Add new sensor types in `self.sensor_templates` in `main.py`
- Extend data parsing in `read_serial()`
- Customize UI colors in `self.colors`

---

## Credits

- Developed by **Rafael A Castro**
- Started: March 22, 2025
- Last updated: September 3rd, 2025
- Special thanks to the open-source Python and Arduino communities

---

## License

MIT License, contact author for further questions or edits.
