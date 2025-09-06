import sys
import json
from PIL import Image, ImageTk
import re
import logging
import webbrowser
from datetime import datetime
import platform
import psutil

print("Python executable:", sys.executable)
import tkinter as tk
from tkinter import messagebox, ttk
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import serial
import serial.tools.list_ports
import threading
import time
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D
from math import radians, sin, cos
import os
import pandas as pd
import io
import contextlib

try:
    from gpt4all import GPT4All

    GPT4ALL_AVAILABLE = True
except ImportError:
    GPT4ALL_AVAILABLE = False

# Application metadata
APP_NAME = "Sealie Sense"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Professional IoT Sensor Data Visualization & Analysis Platform"
APP_AUTHOR = "Castron Technologies"
APP_WEBSITE = "https://castron.tech"
APP_COPYRIGHT = "© 2024 Castron Technologies. All rights reserved."

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("sealink.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class SeaLinkApp(tb.Window):
    """
    Main application class for the SeaLink Dashboard.
    Handles UI, serial communication, data visualization, and user interactions.
    """

    def __init__(self):
        """
        Initialize the SeaLink Dashboard application window and state.
        """
        super().__init__(themename="superhero")
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1400x900")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.resizable(True, True)

        # Set application icon and properties
        try:
            self.iconbitmap("sealink_icon.ico")  # Will be created later
        except:
            pass  # Icon file doesn't exist yet

        # Professional window properties
        self.configure_window_properties()

        # Initialize logging
        logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
        logger.info(f"Application initialized at {datetime.now()}")
        # Modern, professional color palette (black, teal, silver)
        self.night_mode = True
        self.colors = {
            "night": {
                "bg": "#0D1117",  # GitHub dark
                "sidebar": "#161B22",  # GitHub dark sidebar
                "topbar": "#161B22",  # GitHub dark topbar
                "card": "#21262D",  # GitHub dark card
                "fg": "#F0F6FC",  # GitHub light text
                "accent": "#58A6FF",  # GitHub blue
                "highlight": "#7C3AED",  # Purple accent
                "shadow": "#000000",  # Pure black shadow
                "success": "#3FB950",  # GitHub green
                "warning": "#D29922",  # GitHub yellow
                "danger": "#F85149",  # GitHub red
            },
            "day": {
                "bg": "#FFFFFF",  # Pure white
                "sidebar": "#F6F8FA",  # GitHub light sidebar
                "topbar": "#F6F8FA",  # GitHub light topbar
                "card": "#FFFFFF",  # Pure white
                "fg": "#24292F",  # GitHub dark text
                "accent": "#0969DA",  # GitHub blue
                "highlight": "#8250DF",  # Purple accent
                "shadow": "#D0D7DE",  # Light shadow
                "success": "#1A7F37",  # GitHub green
                "warning": "#9A6700",  # GitHub yellow
                "danger": "#CF222E",  # GitHub red
            },
        }
        self.current_theme = "night"
        self.board_names_file = "board_names.json"
        self.settings_file = "settings.json"
        self.board_names = self.load_board_names()
        self.settings = self.load_settings()
        self.selected_board = None

        # Serial
        self.serial_conn = None
        self.is_connected = False
        self.read_thread = None
        self.after_job = None
        # Sidebar state defaults (initialized early to avoid callback races)
        self.sidebar_expanded = True
        self.sidebar_min_width = 48
        self.sidebar_max_width = 220

        # Sensor data
        self.time_data, self.temp_data, self.hum_data = [], [], []
        self.yaw, self.pitch, self.roll = 0, 0, 0
        self.cal_yaw, self.cal_pitch, self.cal_roll = 0, 0, 0
        self.start_time = time.time()

        self.active_sensors = []  # List of dicts: {type, name, port, ...}
        self._template_cache = None  # lazy-loaded sensor templates
        self.generic_streams = {}  # name -> {"time":[], field->[...]} for non-DHT/IMU
        self._sensors_refresh_pending = False
        self._as7341_buf = {"data": {}, "t": 0.0}
        self.as7341_state = {}  # name -> {"bars":[], "canvas":..., "baseline":dict, "smoothed":list}
        self.imu_widgets = {}  # sensor name -> {yaw:Meter, pitch:Meter, roll:Meter}

        self.data_log = []  # List of dicts: {timestamp, sensor, values}
        self.is_recording = False
        self.recording_file = None

        if GPT4ALL_AVAILABLE:
            # NOTE: Model will be downloaded automatically on first use
            self.llm = None  # Will be initialized in init_ai() when needed
        else:
            self.llm = None

        self.build_menu_bar()
        self.build_layout()
        self.refresh_ports()
        self.schedule_simulation()
        self.apply_theme()
        self.init_ai()

    def configure_window_properties(self):
        """Configure professional window properties."""
        # Center window on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

        # Set window state
        self.state("normal")

        # Configure window attributes for professional appearance
        try:
            # Windows-specific attributes
            if sys.platform == "win32":
                self.attributes("-alpha", 0.98)  # Slight transparency for modern look
        except:
            pass

    def build_menu_bar(self):
        """Build professional menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Export Data...", command=self.export_all_data)
        file_menu.add_command(label="Import Data...", command=self.import_data)
        file_menu.add_separator()
        file_menu.add_command(label="Settings...", command=self.show_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Refresh Ports", command=self.refresh_ports)
        tools_menu.add_command(label="Clear All Data", command=self.clear_data)
        tools_menu.add_separator()
        tools_menu.add_command(
            label="System Information", command=self.show_system_info
        )
        tools_menu.add_command(label="View Logs", command=self.show_logs)

        # Analysis menu
        analysis_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Analysis", menu=analysis_menu)
        analysis_menu.add_command(
            label="Calculate Statistics", command=self.calculate_statistics
        )
        analysis_menu.add_command(
            label="Generate Report", command=self.generate_data_report
        )
        analysis_menu.add_command(label="Plot Trends", command=self.plot_data_trends)
        analysis_menu.add_command(
            label="Advanced Analysis", command=self.advanced_data_analysis
        )

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="User Guide", command=self.show_user_guide)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self.show_about_dialog)

    def import_data(self):
        """Import data from CSV file."""
        from tkinter import filedialog

        file = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Import Data",
        )
        if file:
            try:
                import csv

                imported_count = 0
                with open(file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Convert row to our data format
                        values = []
                        for i in range(1, 11):  # Value1 to Value10
                            val = row.get(f"Value{i}", "")
                            values.append(val if val else None)

                        entry = {
                            "timestamp": row.get("Timestamp", ""),
                            "sensor": row.get("Sensor", ""),
                            "values": values,
                        }
                        self.data_log.append(entry)
                        imported_count += 1

                # Refresh the data table
                self.build_data_tab()
                self.show_notification(
                    f"Imported {imported_count} data points", style="success"
                )
                logger.info(f"Imported {imported_count} data points from {file}")

            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to import data: {e}")
                logger.error(f"Data import failed: {e}")

    def show_user_guide(self):
        """Show user guide in a new window."""
        guide_window = tk.Toplevel(self)
        guide_window.title("User Guide")
        guide_window.geometry("800x600")

        text_frame = tb.Frame(guide_window)
        text_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Segoe UI", 10))
        scrollbar = tb.Scrollbar(
            text_frame, orient=tk.VERTICAL, command=text_widget.yview
        )
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        guide_text = f"""
{APP_NAME} User Guide
{"=" * 50}

OVERVIEW
--------
{APP_NAME} is a professional IoT sensor data visualization and analysis platform. 
It provides real-time data collection, visualization, and advanced statistical analysis capabilities.

GETTING STARTED
---------------
1. Connect your Arduino or microcontroller to your computer via USB
2. Go to the Dashboard tab and click "Refresh Ports"
3. Select your device's COM port from the dropdown
4. Click "Connect" to establish communication
5. Your sensor data will appear in real-time

TABS OVERVIEW
-------------
• Dashboard: Real-time sensor data visualization with meters and graphs
• Sensors: Individual sensor monitoring with detailed plots
• Data: Data logging, export, and statistical analysis tools
• AI Assistant: AI-powered data analysis and insights
• About: Application information and system details

DATA RECORDING
--------------
1. Go to the Data tab
2. Click "Start Recording" to begin logging data
3. Choose a location to save your CSV file
4. Data will be automatically logged as it's received
5. Click "Stop Recording" when finished

STATISTICAL ANALYSIS
-------------------
The Data tab includes powerful analysis tools:
• Calculate Statistics: Basic statistical metrics
• Generate Report: Comprehensive data reports
• Plot Trends: Visual trend analysis
• Advanced Analysis: Professional statistical analysis with distributions and correlations
• Export CSV: Filtered data export

AI ASSISTANT
------------
The AI Assistant can help with:
• Data interpretation and insights
• Sensor troubleshooting
• Statistical analysis explanations
• General questions about IoT and sensors

KEYBOARD SHORTCUTS
------------------
• Ctrl+O: Open/Import data
• Ctrl+S: Save/Export data
• Ctrl+R: Refresh ports
• Ctrl+E: Export all data
• F1: Show this help
• F11: Toggle fullscreen

TROUBLESHOOTING
---------------
• If no data appears, check your serial connection
• Ensure your Arduino code matches the expected format
• Try different baud rates (9600, 115200)
• Check the Logs for detailed error information

SUPPORT
-------
For technical support, visit: {APP_WEBSITE}
"""

        text_widget.insert(tk.END, guide_text)
        text_widget.config(state=tk.DISABLED)

    def show_shortcuts(self):
        """Show keyboard shortcuts."""
        shortcuts_window = tk.Toplevel(self)
        shortcuts_window.title("Keyboard Shortcuts")
        shortcuts_window.geometry("500x400")

        text_frame = tb.Frame(shortcuts_window)
        text_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 10))
        text_widget.pack(fill=BOTH, expand=True)

        shortcuts_text = """
KEYBOARD SHORTCUTS
==================

File Operations:
  Ctrl+O          Open/Import data file
  Ctrl+S          Save/Export data
  Ctrl+E          Export all data
  Ctrl+Q          Quit application

Data Operations:
  Ctrl+R          Refresh serial ports
  Ctrl+C          Clear all data
  Ctrl+T          Toggle recording
  F5              Refresh data display

Navigation:
  Ctrl+1          Go to Dashboard tab
  Ctrl+2          Go to Sensors tab
  Ctrl+3          Go to Data tab
  Ctrl+4          Go to AI Assistant tab
  Ctrl+5          Go to About tab

Analysis:
  Ctrl+Shift+S    Calculate statistics
  Ctrl+Shift+R    Generate report
  Ctrl+Shift+P    Plot trends
  Ctrl+Shift+A    Advanced analysis

Help:
  F1              Show user guide
  F2              Show keyboard shortcuts
  F11             Toggle fullscreen mode
  Ctrl+?          Show about dialog

AI Assistant:
  Enter           Send message (when focused)
  Ctrl+Enter      Send message (anywhere)
  Escape          Clear input field
"""

        text_widget.insert(tk.END, shortcuts_text)
        text_widget.config(state=tk.DISABLED)

    def show_about_dialog(self):
        """Show about dialog."""
        about_window = tk.Toplevel(self)
        about_window.title("About")
        about_window.geometry("500x400")
        about_window.resizable(False, False)

        # Center the window
        about_window.transient(self)
        about_window.grab_set()

        main_frame = tb.Frame(about_window)
        main_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        # Logo/icon
        logo_label = tb.Label(
            main_frame, text="🌊", font=("Segoe UI", 48), bootstyle="info"
        )
        logo_label.pack(pady=(0, 20))

        # App info
        tb.Label(
            main_frame,
            text=APP_NAME,
            font=("Segoe UI", 20, "bold"),
            bootstyle="primary",
        ).pack()

        tb.Label(
            main_frame,
            text=f"Version {APP_VERSION}",
            font=("Segoe UI", 12),
            bootstyle="secondary",
        ).pack(pady=(5, 10))

        tb.Label(
            main_frame,
            text=APP_DESCRIPTION,
            font=("Segoe UI", 10),
            bootstyle="info",
            wraplength=400,
        ).pack(pady=(0, 20))

        # Company info
        tb.Label(
            main_frame,
            text=f"Developed by {APP_AUTHOR}",
            font=("Segoe UI", 10),
            bootstyle="warning",
        ).pack()

        tb.Label(
            main_frame, text=APP_COPYRIGHT, font=("Segoe UI", 9), bootstyle="secondary"
        ).pack(pady=(5, 20))

        # Buttons
        button_frame = tb.Frame(main_frame)
        button_frame.pack()

        tb.Button(
            button_frame,
            text="Visit Website",
            command=lambda: webbrowser.open(APP_WEBSITE),
            bootstyle="info-outline",
        ).pack(side=tk.LEFT, padx=(0, 10))

        tb.Button(
            button_frame,
            text="Close",
            command=about_window.destroy,
            bootstyle="primary",
        ).pack(side=tk.LEFT)

    def load_settings(self):
        """Load settings from settings.json file."""
        try:
            with open(self.settings_file, "r") as f:
                settings = json.load(f)
                # Defaults
                settings.setdefault("baud_rate", 9600)
                settings.setdefault("theme", "superhero")
                settings.setdefault("ai_provider", "none")  # auto|openai|gpt4all|none
                settings.setdefault("openai_api_key", "")
                return settings
        except:
            # Return default settings if file doesn't exist or is invalid
            return {
                "baud_rate": 9600,
                "theme": "superhero",
                "ai_provider": "simple",
                "openai_api_key": "",
            }

    def save_settings(self):
        """Save current settings to settings.json file."""
        with open(self.settings_file, "w") as f:
            json.dump(self.settings, f, indent=2)

    def load_board_names(self):
        try:
            with open(self.board_names_file, "r") as f:
                return json.load(f)
        except:
            return {}

    def toggle_recording(self):
        if not self.is_recording:
            import datetime
            import os

            self.is_recording = True
            self.record_btn.config(text="Stop Recording", bootstyle="danger-outline")
            os.makedirs("data", exist_ok=True)
            filepath = os.path.join(
                "data",
                f"sealink_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            )
            self.recording_file = open(filepath, "w", newline="")
            self.recording_path = filepath
            import csv

            self.csv_writer = csv.writer(self.recording_file)
            # Wide header to accommodate sensors with many fields
            header = ["Timestamp", "Sensor"] + [f"Value{i}" for i in range(1, 11)]
            self.csv_writer.writerow(header)
            self.show_notification(
                f"Recording to {os.path.basename(filepath)}", style="success"
            )
            # Update status on Data tab if visible
            if hasattr(self, "rec_status_lbl") and self.rec_status_lbl.winfo_exists():
                self.rec_status_lbl.config(text=f"Recording to: {self.recording_path}")
        else:
            self.is_recording = False
            self.record_btn.config(text="Start Recording", bootstyle="primary-outline")
            if self.recording_file:
                self.recording_file.close()
                self.recording_file = None
            self.recording_path = ""
            self.show_notification("Recording stopped", style="warning")
            if hasattr(self, "rec_status_lbl") and self.rec_status_lbl.winfo_exists():
                self.rec_status_lbl.config(text="Not recording")

    def log_data(self, sensor, values):
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {"timestamp": timestamp, "sensor": sensor, "values": values}
        self.data_log.append(entry)
        # Append to Data table live if present
        try:
            if hasattr(self, "data_table") and self.data_table.winfo_exists():
                vals = list(values)[:10]
                if len(vals) < 10:
                    vals += [""] * (10 - len(vals))
                self.data_table.insert("", "end", values=(timestamp, sensor, *vals))

                # Update data summary
                if hasattr(self, "data_summary"):
                    self.data_summary.config(text=f"Data Points: {len(self.data_log)}")
        except Exception:
            pass
        if (
            self.is_recording
            and hasattr(self, "recording_path")
            and self.recording_path
        ):
            row = [timestamp, sensor] + list(values)[:10]
            if len(row) < 12:
                row += [""] * (12 - len(row))
            try:
                import csv

                with open(self.recording_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(row)
            except Exception as e:
                logger.error(f"Failed to write to recording file: {e}")

    def save_board_names(self):
        with open(self.board_names_file, "w") as f:
            json.dump(self.board_names, f)

    def build_layout(self):
        # Main container
        self.container = tb.Frame(self)
        self.container.pack(fill=BOTH, expand=True)

        # Topbar (with hamburger icon on the left)
        self.topbar = tb.Frame(self.container, bootstyle="dark")
        self.topbar.pack(side=TOP, fill=X)
        self.topbar.pack_propagate(False)
        self.topbar.configure(height=60)
        # Hamburger icon in topbar (custom canvas for high contrast)
        self.hamburger_btn = tk.Frame(self.topbar, width=36, height=36, bg="#20CFCF")
        self.hamburger_btn.pack_propagate(False)
        self.hamburger_btn.pack(side=LEFT, padx=10, pady=12)
        self.hamburger_canvas = tk.Canvas(
            self.hamburger_btn, width=24, height=18, bg="#20CFCF", highlightthickness=0
        )
        self.hamburger_canvas.pack(expand=True)
        # draw three white bars
        self.hamburger_canvas.create_rectangle(0, 0, 24, 3, fill="white", outline="")
        self.hamburger_canvas.create_rectangle(0, 7, 24, 10, fill="white", outline="")
        self.hamburger_canvas.create_rectangle(0, 14, 24, 17, fill="white", outline="")
        # click bindings
        self.hamburger_btn.bind("<Button-1>", self.toggle_sidebar)
        self.hamburger_canvas.bind("<Button-1>", self.toggle_sidebar)

        # simple hover effect
        def _hover_in(e):
            self.hamburger_btn.configure(bg="#1bb3b3")
            self.hamburger_canvas.configure(bg="#1bb3b3")

        def _hover_out(e):
            self.hamburger_btn.configure(bg="#20CFCF")
            self.hamburger_canvas.configure(bg="#20CFCF")

        self.hamburger_btn.bind("<Enter>", _hover_in)
        self.hamburger_btn.bind("<Leave>", _hover_out)
        self.hamburger_canvas.bind("<Enter>", _hover_in)
        self.hamburger_canvas.bind("<Leave>", _hover_out)
        self.add_hover(self.hamburger_btn)
        self.create_tooltip(self.hamburger_btn, "Toggle sidebar")
        self.export_btn = tb.Button(
            self.topbar,
            text="Export CSV",
            command=self.export_csv,
            bootstyle="info-outline",
        )
        self.export_btn.pack(side=RIGHT, padx=10)
        self.add_hover(self.export_btn)
        self.create_tooltip(self.export_btn, "Export sensor data to CSV")
        # Serial controls
        self.port_var = tk.StringVar()
        self.port_menu = tb.Combobox(
            self.topbar, textvariable=self.port_var, width=18, bootstyle="info"
        )
        self.port_menu.pack(side=LEFT, padx=10)
        self.create_tooltip(self.port_menu, "Select serial port")
        self.refresh_btn = tb.Button(
            self.topbar,
            text="Refresh",
            command=self.refresh_ports,
            bootstyle="secondary",
        )
        self.refresh_btn.pack(side=LEFT, padx=5)
        self.add_hover(self.refresh_btn)
        self.create_tooltip(self.refresh_btn, "Refresh available ports")
        self.connect_btn = tb.Button(
            self.topbar,
            text="Connect",
            command=self.connect_serial,
            bootstyle="success",
        )
        self.connect_btn.pack(side=LEFT, padx=5)
        self.add_hover(self.connect_btn)
        self.create_tooltip(self.connect_btn, "Connect to selected port")
        self.disconnect_btn = tb.Button(
            self.topbar,
            text="Disconnect",
            command=self.disconnect_serial,
            bootstyle="danger",
            state=DISABLED,
        )
        self.disconnect_btn.pack(side=LEFT, padx=5)
        self.add_hover(self.disconnect_btn)
        self.create_tooltip(self.disconnect_btn, "Disconnect from port")
        self.calib_btn = tb.Button(
            self.topbar,
            text="Calibrate",
            command=self.calibrate_sensor,
            bootstyle="warning",
            state=DISABLED,
        )
        self.calib_btn.pack(side=LEFT, padx=5)
        self.add_hover(self.calib_btn)
        self.create_tooltip(self.calib_btn, "Calibrate orientation")
        self.record_btn = tb.Button(
            self.topbar,
            text="Start Recording",
            command=self.toggle_recording,
            bootstyle="primary-outline",
        )
        self.record_btn.pack(side=RIGHT, padx=10)
        self.add_hover(self.record_btn)
        self.create_tooltip(self.record_btn, "Start/Stop data recording")

        # AI status label (right side)
        self.ai_status_lbl = tb.Label(
            self.topbar,
            text="AI: Initializing...",
            bootstyle="info",
            font=("Segoe UI", 9),
        )
        self.ai_status_lbl.pack(side=RIGHT, padx=10)

        # Connection status label (right side)
        self.status_lbl = tb.Label(
            self.topbar,
            text="Disconnected",
            bootstyle="warning",
            font=("Segoe UI", 11, "bold"),
        )
        self.status_lbl.pack(side=RIGHT, padx=20)

        # Main content area (cards)
        self.content = tb.Frame(self.container)  # removed bg argument
        self.content.pack(side=LEFT, fill=BOTH, expand=True)
        self.tabs = []
        # Dashboard tab
        self.tab_dashboard = tb.Frame(self.content)  # removed bg argument
        self.tabs.append(self.tab_dashboard)
        # Sensors tab
        self.tab_sensors = tb.Frame(self.content)  # removed bg argument
        self.tabs.append(self.tab_sensors)
        # Data tab
        self.tab_data = tb.Frame(self.content)  # removed bg argument
        self.tabs.append(self.tab_data)
        # Settings tab
        self.tab_settings = tb.Frame(self.content)  # removed bg argument
        self.tabs.append(self.tab_settings)
        # About tab
        self.tab_about = tb.Frame(self.content)  # removed bg argument
        self.tabs.append(self.tab_about)
        for tab in self.tabs:
            tab.place(relx=0.02, rely=0.04, relwidth=0.96, relheight=0.92)
            tab.configure(borderwidth=2, relief="groove")
        self.build_dashboard()
        self.build_sensors_tab()
        self.build_data_tab()
        self.build_settings_tab()
        self.build_about_tab()
        self.show_tab(0)

        # Sidebar (classic packed)
        self.sidebar = tb.Frame(self.container, width=180, bootstyle="dark")
        self.sidebar.pack(side=LEFT, fill=Y)
        self.sidebar.pack_propagate(False)

    def add_hover(self, widget):
        def on_enter(e):
            widget.configure(cursor="hand2")
            widget.configure(bootstyle="primary-outline")

        def on_leave(e):
            widget.configure(cursor="arrow")
            # Restore original style
            style = widget.cget("bootstyle")
            if "primary" in style:
                widget.configure(
                    bootstyle=style.replace("primary-outline", "secondary")
                )

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def create_tooltip(self, widget, text):
        """
        Attach a tooltip to a widget.
        """

        def on_enter(event):
            self.tooltip = tk.Toplevel(widget)
            self.tooltip.wm_overrideredirect(True)
            x = widget.winfo_rootx() + 20
            y = widget.winfo_rooty() + 20
            self.tooltip.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                self.tooltip,
                text=text,
                background="#333",
                foreground="#fff",
                relief="solid",
                borderwidth=1,
                font=("Segoe UI", 9),
            )
            label.pack(ipadx=4, ipady=2)

        def on_leave(event):
            if hasattr(self, "tooltip"):
                self.tooltip.destroy()

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def apply_theme(self):
        c = self.colors["night" if self.night_mode else "day"]
        # Set background for main window (classic Tk root)
        self.configure(bg=c["bg"])
        # Guard: layout may not be built yet
        if hasattr(self, "sidebar") and self.sidebar is not None:
            # Only set bg/fg for classic Tk widgets in sidebar
            try:
                for w in self.sidebar.winfo_children():
                    if isinstance(w, tk.Frame) or isinstance(w, tk.Label):
                        try:
                            w.configure(bg=c["sidebar"], fg=c["fg"])
                        except:
                            pass
            except Exception:
                pass
            # Use bootstyle for ttkbootstrap widgets
            try:
                self.sidebar.configure(
                    bootstyle="dark" if self.night_mode else "warning"
                )
            except Exception:
                pass
        if hasattr(self, "topbar") and self.topbar is not None:
            try:
                self.topbar.configure(
                    bootstyle="dark" if self.night_mode else "warning"
                )
            except Exception:
                pass
        # Update plot backgrounds if needed
        try:
            if hasattr(self, "fig") and hasattr(self, "ax1"):
                self.fig.patch.set_facecolor(c["card"])
                self.ax1.set_facecolor(c["card"])
                if hasattr(self, "canvas"):
                    self.canvas.draw()
            if hasattr(self, "ax3d") and hasattr(self, "canvas3d"):
                self.ax3d.set_facecolor(c["card"])
                self.canvas3d.draw()
        except Exception:
            pass

    def toggle_theme(self):
        """
        Toggle between dark and light themes.
        """
        self.night_mode = not self.night_mode
        self.current_theme = "night" if self.night_mode else "day"
        self.apply_theme()

    def show_about(self):
        """
        Show the About dialog with app info.
        """
        messagebox.showinfo(
            "About SeaLink",
            "SeaLink Dashboard\nVersion 1.0\n\nA professional dashboard for sensor data visualization.\n© 2024 Your Company",
        )

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        # Show saved board names if available
        display_ports = []
        for port in ports:
            name = self.board_names.get(port, None)
            if name:
                display_ports.append(f"{name} ({port})")
            else:
                display_ports.append(port)
        self.port_menu["values"] = display_ports
        if display_ports:
            self.port_var.set(display_ports[0])

    def get_selected_port(self):
        val = self.port_var.get()
        if "(" in val and val.endswith(")"):
            return val.split("(")[-1][:-1].strip()
        return val

    def connect_serial(self):
        port = self.get_selected_port()
        try:
            baud = self.settings.get("baud_rate", 9600)
            print(f"[DEBUG] Attempting to open serial port: {port} at {baud} baud")
            self.serial_conn = serial.Serial(port, baud, timeout=1)
            print(f"[DEBUG] Serial port {port} opened: {self.serial_conn.is_open}")
            time.sleep(2)
            self.is_connected = True
            self.status_lbl.config(text=f"Connected: {port}", bootstyle="success")
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
            self.calib_btn.config(state=NORMAL)
            self.send_flash()
            self.read_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.read_thread.start()
            # Prompt to name the board if not already named
            if port not in self.board_names:
                self.prompt_name_board(port)
        except Exception as e:
            print(f"[ERROR] Failed to open serial port {port}: {e}")
            self.show_connection_error_popup(port, str(e))
            self.show_notification(f"Serial connect error: {e}", style="danger")

    def show_connection_error_popup(self, port, error_msg):
        """Show a custom, professional connection error popup."""
        popup = tk.Toplevel(self)
        popup.title("Connection Failed")
        popup.geometry("450x300")
        popup.resizable(False, False)
        popup.configure(bg="#2c3e50")

        # Center the popup
        popup.transient(self)
        popup.grab_set()

        # Header
        header_frame = tk.Frame(popup, bg="#e74c3c", height=60)
        header_frame.pack(fill=X)
        header_frame.pack_propagate(False)

        error_icon = tk.Label(
            header_frame, text="⚠️", font=("Segoe UI", 24), bg="#e74c3c", fg="white"
        )
        error_icon.pack(side=LEFT, padx=20, pady=15)

        title_label = tk.Label(
            header_frame,
            text="Connection Failed",
            font=("Segoe UI", 16, "bold"),
            bg="#e74c3c",
            fg="white",
        )
        title_label.pack(side=LEFT, padx=10, pady=15)

        # Content
        content_frame = tk.Frame(popup, bg="#2c3e50")
        content_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        # Error details
        tk.Label(
            content_frame,
            text="Unable to connect to the selected port:",
            font=("Segoe UI", 12, "bold"),
            bg="#2c3e50",
            fg="#ecf0f1",
        ).pack(anchor="w", pady=(0, 5))

        port_label = tk.Label(
            content_frame,
            text=f"Port: {port}",
            font=("Segoe UI", 11),
            bg="#2c3e50",
            fg="#bdc3c7",
        )
        port_label.pack(anchor="w", pady=2)

        baud_label = tk.Label(
            content_frame,
            text=f"Baud Rate: {self.settings.get('baud_rate', 9600)}",
            font=("Segoe UI", 11),
            bg="#2c3e50",
            fg="#bdc3c7",
        )
        baud_label.pack(anchor="w", pady=2)

        # Error message
        error_frame = tk.Frame(content_frame, bg="#34495e", relief="solid", bd=1)
        error_frame.pack(fill=X, pady=10)

        tk.Label(
            error_frame,
            text="Error Details:",
            font=("Segoe UI", 10, "bold"),
            bg="#34495e",
            fg="#ecf0f1",
        ).pack(anchor="w", padx=10, pady=(10, 5))

        error_text = tk.Text(
            error_frame,
            height=4,
            wrap="word",
            bg="#34495e",
            fg="#ecf0f1",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
        )
        error_text.pack(fill=X, padx=10, pady=(0, 10))
        error_text.insert("1.0", error_msg)
        error_text.config(state="disabled")

        # Troubleshooting tips
        tk.Label(
            content_frame,
            text="Troubleshooting Tips:",
            font=("Segoe UI", 11, "bold"),
            bg="#2c3e50",
            fg="#ecf0f1",
        ).pack(anchor="w", pady=(15, 5))

        tips = [
            "• Check if the device is properly connected",
            "• Verify the correct port is selected",
            "• Try a different baud rate (9600, 115200)",
            "• Restart the device and try again",
            "• Check if another application is using the port",
        ]

        for tip in tips:
            tk.Label(
                content_frame,
                text=tip,
                font=("Segoe UI", 9),
                bg="#2c3e50",
                fg="#95a5a6",
            ).pack(anchor="w", padx=10)

        # Buttons
        button_frame = tk.Frame(popup, bg="#2c3e50")
        button_frame.pack(fill=X, padx=20, pady=20)

        def refresh_ports_and_close():
            self.refresh_ports()
            popup.destroy()

        def open_settings_and_close():
            popup.destroy()
            self.show_settings()

        refresh_btn = tk.Button(
            button_frame,
            text="Refresh Ports",
            command=refresh_ports_and_close,
            bg="#3498db",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
        )
        refresh_btn.pack(side=LEFT, padx=5)

        settings_btn = tk.Button(
            button_frame,
            text="Open Settings",
            command=open_settings_and_close,
            bg="#95a5a6",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
        )
        settings_btn.pack(side=LEFT, padx=5)

        close_btn = tk.Button(
            button_frame,
            text="Close",
            command=popup.destroy,
            bg="#e74c3c",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
        )
        close_btn.pack(side=RIGHT, padx=5)

        # Hover effects
        def on_enter(e):
            e.widget.configure(
                bg="#2980b9"
                if e.widget == refresh_btn
                else "#7f8c8d"
                if e.widget == settings_btn
                else "#c0392b"
            )

        def on_leave(e):
            e.widget.configure(
                bg="#3498db"
                if e.widget == refresh_btn
                else "#95a5a6"
                if e.widget == settings_btn
                else "#e74c3c"
            )

        for btn in [refresh_btn, settings_btn, close_btn]:
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)

        # Focus and center
        popup.focus_set()
        popup.wait_window()

    def disconnect_serial(self):
        self.is_connected = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.status_lbl.config(text="Disconnected", bootstyle="warning")
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
        self.calib_btn.config(state=DISABLED)

    def send_flash(self):
        """
        Send a flash command to the connected device (if supported).
        """
        try:
            for _ in range(2):
                self.serial_conn.write(b"F")
                time.sleep(0.2)
        except:
            pass

    def calibrate_sensor(self):
        """
        Calibrate the orientation sensor by setting the current values as zero reference.
        """
        self.cal_yaw = self.yaw
        self.cal_pitch = self.pitch
        self.cal_roll = self.roll
        self.show_notification("Calibrated!", style="success")
        self.status_lbl.config(text="Calibrated!", bootstyle="success")
        self.after(
            2000,
            lambda: self.status_lbl.config(
                text="Connected" if self.is_connected else "Disconnected",
                bootstyle="success" if self.is_connected else "warning",
            ),
        )

    def read_serial(self):
        """
        Continuously read data from the serial port in a background thread.
        """
        no_data_counter = 0
        while self.is_connected:
            try:
                line = (
                    self.serial_conn.readline()
                    .decode("utf-8", errors="replace")
                    .strip()
                )
                if not line:
                    no_data_counter += 1
                    if no_data_counter == 10:
                        print("[WARNING] No serial data received after 10 reads.")
                        self.show_notification(
                            "No serial data received! Check Arduino.", style="warning"
                        )
                    continue
                no_data_counter = 0
                self.log_serial_debug(line)
                print(f"[SERIAL] {line}")

                # AS7341 multi-line aggregator
                if self._try_parse_as7341(line):
                    continue

                # CSV-like sensor line (e.g., 'MPU6050,3.2,1.0')
                if self._parse_csv_sensor_line(line):
                    continue

                # Template-first parsing for selected sensors
                parsed_any = False
                for sensor in list(self.active_sensors):
                    rx = sensor.get("_compiled")
                    if not rx:
                        continue
                    m = rx.match(line)
                    if not m:
                        continue
                    data = m.groupdict()
                    self._ingest_template_sensor(sensor, data)
                    parsed_any = True
                    break
                if parsed_any:
                    continue

                # Legacy formats fallback (DHT/IMU)
                # ... existing legacy parsing remains unchanged ...
                if line.startswith("YAW"):
                    try:
                        parts = line.replace(",", " ").split()
                        self.yaw = float(
                            [p for p in parts if p.startswith("YAW")][0].split(":")[1]
                        )
                        self.pitch = float(
                            [p for p in parts if p.startswith("PITCH")][0].split(":")[1]
                        )
                        self.roll = float(
                            [p for p in parts if p.startswith("ROLL")][0].split(":")[1]
                        )
                        temp_f = float(
                            [p for p in parts if p.startswith("TEMP")][0].split(":")[1]
                        )
                        hum = float(
                            [p for p in parts if p.startswith("HUM")][0].split(":")[1]
                        )
                        # Convert Fahrenheit to Celsius
                        temp_c = (temp_f - 32) * 5 / 9
                        self.append_dht_data(temp_c, hum)
                        self.log_data(
                            "3D Orientation", (self.yaw, self.pitch, self.roll)
                        )
                        self.update_3d_orientation()
                        self.update_all_meters()  # Update meters with new data
                        print(
                            f"[PARSED] YAW:{self.yaw}, PITCH:{self.pitch}, ROLL:{self.roll}, TEMP:{temp_f}°F->{temp_c:.1f}°C, HUM:{hum}"
                        )
                        self.show_notification("Data received", style="success")
                        self.status_lbl.config(
                            text="Data received", bootstyle="success"
                        )
                        self.after(
                            1000,
                            lambda: self.status_lbl.config(
                                text="Connected", bootstyle="success"
                            ),
                        )
                    except Exception as e:
                        print(f"[ERROR] YAW parse error: {e}")
                        self.show_notification(f"YAW parse error: {e}", style="danger")
                elif line.startswith("TEMP") or line.startswith("DHT"):
                    # Example: TEMP:23.5 HUM:45.2 or DHT:23.5 HUM:45.2
                    try:
                        parts = line.replace(",", " ").split()
                        temp_f = float(
                            [
                                p
                                for p in parts
                                if p.startswith("TEMP") or p.startswith("DHT")
                            ][0].split(":")[1]
                        )
                        hum = float(
                            [p for p in parts if p.startswith("HUM")][0].split(":")[1]
                        )
                        # Convert Fahrenheit to Celsius
                        temp_c = (temp_f - 32) * 5 / 9
                        self.append_dht_data(temp_c, hum)
                        self.log_data("DHT Sensor", (temp_c, hum))
                        print(f"[PARSED] TEMP:{temp_f}°F->{temp_c:.1f}°C, HUM:{hum}")
                        self.show_notification("DHT data received", style="success")
                    except Exception as e:
                        print(f"[ERROR] DHT parse error: {e}")
                        self.show_notification(f"DHT parse error: {e}", style="danger")
                elif line:
                    # Try to parse generic key:value pairs
                    try:
                        data = dict()
                        for part in line.replace(",", " ").split():
                            if ":" in part:
                                k, v = part.split(":", 1)
                                data[k.strip().upper()] = float(v.strip())

                        # Check for MPU6050 data (common formats)
                        if "YAW" in data and "PITCH" in data and "ROLL" in data:
                            self.yaw = data["YAW"]
                            self.pitch = data["PITCH"]
                            self.roll = data["ROLL"]
                            self.log_data(
                                "3D Orientation", (self.yaw, self.pitch, self.roll)
                            )
                            self.update_3d_orientation()
                            self.update_all_meters()  # Update meters with new data
                            print(
                                f"[PARSED] MPU6050 - YAW:{self.yaw}, PITCH:{self.pitch}, ROLL:{self.roll}"
                            )
                            self.show_notification(
                                "MPU6050 data received", style="success"
                            )
                        elif "TEMP" in data and "HUM" in data:
                            # Convert Fahrenheit to Celsius
                            temp_f = data["TEMP"]
                            temp_c = (temp_f - 32) * 5 / 9
                            self.append_dht_data(temp_c, data["HUM"])
                            self.log_data("DHT Sensor", (temp_c, data["HUM"]))
                            print(
                                f"[PARSED] DHT - TEMP:{temp_f}°F->{temp_c:.1f}°C, HUM:{data['HUM']}"
                            )
                            self.show_notification(
                                "DHT data received (generic)", style="success"
                            )
                        elif "TEMP" in data:
                            # If only temperature is available, convert and use it
                            temp_f = data["TEMP"]
                            temp_c = (temp_f - 32) * 5 / 9
                            self.append_dht_data(temp_c, 0)  # Set humidity to 0
                            self.log_data("Temperature", (temp_c,))
                            print(f"[PARSED] TEMP only: {temp_f}°F->{temp_c:.1f}°C")
                            self.show_notification(
                                "Temperature data received", style="success"
                            )
                        elif "HUM" in data:
                            # If only humidity is available, use it
                            self.append_dht_data(0, data["HUM"])  # Set temperature to 0
                            self.log_data("Humidity", (data["HUM"],))
                            print(f"[PARSED] HUM only: {data['HUM']}")
                            self.show_notification(
                                "Humidity data received", style="success"
                            )
                        else:
                            print(f"[WARNING] Unrecognized data format: {line}")
                            self.show_notification(
                                f"Unrecognized data: {line}", style="warning"
                            )
                    except Exception as e:
                        print(f"[ERROR] Parse error: {e}")
                        self.show_notification(f"Parse error: {e}", style="danger")
                # Add more formats as needed
            except Exception as e:
                self.log_serial_debug(f"Error: {e}")
                print(f"[SERIAL ERROR] {e}")
                continue

    def append_dht_data(self, temp, hum):
        """
        Append new DHT sensor data to the arrays and update the time axis.
        """
        t = time.time() - self.start_time
        self.time_data.append(t)
        self.temp_data.append(temp)
        self.hum_data.append(hum)
        # Keep only the last 100 points for plotting
        self.time_data = self.time_data[-100:]
        self.temp_data = self.temp_data[-100:]
        self.hum_data = self.hum_data[-100:]
        self.update_dht_plot()
        self.update_all_meters()  # Update meters with new data

    def update_dht_plot(self):
        # Redraw the DHT plot if it exists
        if hasattr(self, "fig") and hasattr(self, "ax1"):
            self.ax1.clear()
            if self.is_connected and self.time_data:
                self.ax1.plot(
                    self.time_data, self.temp_data, color="#304674", label="Temp"
                )
                self.ax1.plot(
                    self.time_data, self.hum_data, color="#3A506B", label="Humidity"
                )
                self.ax1.set_ylabel("Value")
                self.ax1.set_xlabel("Time (s)")
                self.ax1.legend()
            else:
                self.ax1.set_title("No data")
            self.ax1.grid(True)
            if hasattr(self, "canvas"):
                self.canvas.draw()

    def update_all_meters(self):
        """Update lightweight UI (quick stats) without rebuilding full views to avoid flashing."""
        try:
            if hasattr(self, "quick_stats"):
                self.quick_stats.config(text=self.get_quick_stats())
        except Exception:
            pass

    def build_sensors_tab(self):
        for w in self.tab_sensors.winfo_children():
            w.destroy()
        tb.Label(self.tab_sensors, text="Sensors", font=("Segoe UI", 18, "bold")).pack(
            pady=20
        )
        sensors_frame = tb.Frame(self.tab_sensors)
        sensors_frame.pack(pady=10, fill=BOTH, expand=True)
        # Grid layout: 2 columns
        row = 0
        col = 0
        for sensor in self.active_sensors:
            holder = tb.Frame(sensors_frame)
            holder.grid(row=row, column=col, padx=10, pady=10, sticky="n")
            self.build_sensor_card(holder, sensor)
            col += 1
            if col >= 2:
                col = 0
                row += 1

    def request_sensors_refresh(self):
        if self._sensors_refresh_pending:
            return
        self._sensors_refresh_pending = True
        self.after(250, self._do_sensors_refresh)

    def _do_sensors_refresh(self):
        self._sensors_refresh_pending = False
        try:
            self.build_sensors_tab()
        except Exception:
            pass

    def build_sensor_card(self, parent, sensor):
        # Enhanced card styling with modern look
        card = tb.Frame(parent, bootstyle="secondary", borderwidth=1, relief="solid")
        card.pack(pady=15, padx=15, fill=X)

        # Add subtle shadow effect through padding
        shadow_frame = tb.Frame(card, bootstyle="dark")
        shadow_frame.pack(fill=BOTH, expand=True, padx=2, pady=2)
        header_row = tb.Frame(shadow_frame)
        header_row.pack(fill=X, pady=(15, 10), padx=15)
        tb.Label(
            header_row,
            text=f"{sensor['icon']} {sensor['name']}",
            font=("Segoe UI", 16, "bold"),
            bootstyle="primary",
        ).pack(side=LEFT)
        status = "Connected" if self.is_connected else "Not Connected"
        tb.Label(
            header_row,
            text=status,
            font=("Segoe UI", 11, "bold"),
            bootstyle="success" if self.is_connected else "danger",
        ).pack(side=LEFT, padx=(20, 0))
        tb.Button(
            header_row,
            text="Configure",
            command=lambda s=sensor: self.configure_sensor(s),
            bootstyle="primary-outline",
        ).pack(side=RIGHT)
        tb.Button(
            header_row,
            text="Remove",
            command=lambda: self.remove_sensor(sensor),
            bootstyle="danger-outline",
        ).pack(side=RIGHT, padx=5)
        # Live data/graph and meters
        s_type = sensor.get("type", "").upper()
        s_name = sensor.get("name", s_type)
        if s_type in ("DHT", "DHT11", "DHT22"):
            temp_val = self.temp_data[-1] if self.temp_data else 0
            hum_val = self.hum_data[-1] if self.hum_data else 0
            meter_row = tb.Frame(shadow_frame)
            meter_row.pack(pady=10, padx=15)
            tb.Meter(
                meter_row,
                amountused=temp_val,
                metertype="full",
                subtext="Temp (°C)",
                bootstyle="danger",
                stripethickness=6,
                interactive=False,
                amounttotal=60,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            ).pack(side=LEFT, padx=10)
            tb.Meter(
                meter_row,
                amountused=hum_val,
                metertype="full",
                subtext="Humidity (%)",
                bootstyle="info",
                stripethickness=6,
                interactive=False,
                amounttotal=100,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            ).pack(side=LEFT, padx=10)
            self.build_dht_plot(parent=card, compact=True, sensor_name=sensor["name"])
        elif s_type == "MPU6050":
            meter_row = tb.Frame(shadow_frame)
            meter_row.pack(pady=10, padx=15)
            yaw_m = tb.Meter(
                meter_row,
                amountused=self.yaw,
                metertype="full",
                subtext="Yaw (°)",
                bootstyle="primary",
                stripethickness=6,
                interactive=False,
                amounttotal=180,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            )
            yaw_m.pack(side=LEFT, padx=10)
            pitch_m = tb.Meter(
                meter_row,
                amountused=self.pitch,
                metertype="full",
                subtext="Pitch (°)",
                bootstyle="warning",
                stripethickness=6,
                interactive=False,
                amounttotal=90,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            )
            pitch_m.pack(side=LEFT, padx=10)
            roll_m = tb.Meter(
                meter_row,
                amountused=self.roll,
                metertype="full",
                subtext="Roll (°)",
                bootstyle="success",
                stripethickness=6,
                interactive=False,
                amounttotal=180,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            )
            roll_m.pack(side=LEFT, padx=10)
            self.imu_widgets[s_name] = {"yaw": yaw_m, "pitch": pitch_m, "roll": roll_m}
            self.build_3d_plot(parent=card, compact=True)
        elif s_type == "ITG/MPU6050":
            meter_row = tb.Frame(shadow_frame)
            meter_row.pack(pady=10, padx=15)
            yaw_m = tb.Meter(
                meter_row,
                amountused=self.yaw,
                metertype="full",
                subtext="Yaw (°)",
                bootstyle="primary",
                stripethickness=6,
                interactive=False,
                amounttotal=180,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            )
            yaw_m.pack(side=LEFT, padx=10)
            pitch_m = tb.Meter(
                meter_row,
                amountused=self.pitch,
                metertype="full",
                subtext="Pitch (°)",
                bootstyle="warning",
                stripethickness=6,
                interactive=False,
                amounttotal=90,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            )
            pitch_m.pack(side=LEFT, padx=10)
            roll_m = tb.Meter(
                meter_row,
                amountused=self.roll,
                metertype="full",
                subtext="Roll (°)",
                bootstyle="success",
                stripethickness=6,
                interactive=False,
                amounttotal=180,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            )
            roll_m.pack(side=LEFT, padx=10)
            self.imu_widgets[s_name] = {"yaw": yaw_m, "pitch": pitch_m, "roll": roll_m}
            self.build_3d_plot(parent=card, compact=True)
        elif s_type in ("BMP280", "TDS", "SOIL", "LDR", "DS18B20", "UV"):
            # simple compact plot using generic_streams
            stream = self.generic_streams.get(s_name, {})
            if not stream:
                tb.Label(card, text="No data", font=("Segoe UI", 10, "italic")).pack(
                    pady=5
                )
            else:
                fig = Figure(figsize=(3.6, 2.0), dpi=100)
                ax = fig.add_subplot(111)
                t = stream.get("time", [])
                for f in sensor.get("fields", []):
                    ax.plot(
                        t, stream.get(f, []), label=sensor.get("_labels", {}).get(f, f)
                    )
                ax.set_xlabel("Time (s)")
                ax.set_ylabel("Value")
                ax.legend(fontsize=8, frameon=True)
                ax.grid(True, linestyle="--", alpha=0.4)
                fig.tight_layout(pad=1.2)
                canvas = FigureCanvasTkAgg(fig, master=card)
                canvas.get_tk_widget().pack(padx=10, pady=10)
        elif s_type == "AS7341":
            # Build bar chart for spectrometer
            state = self.as7341_state.setdefault(
                s_name, {"baseline": {}, "smoothed": [0.0] * 10}
            )
            fig = Figure(figsize=(5, 2.4), dpi=100)
            ax = fig.add_subplot(111)
            wavelengths = ["415", "445", "480", "515", "555", "590", "630", "680"]
            bars = ax.bar(wavelengths, [0] * 8, color="#20CFCF")
            ax.set_ylim(0, 1.2)
            ax.set_ylabel("Normalized Intensity")
            ax.set_xlabel("Wavelength (nm)")
            ax.grid(True, linestyle="--", alpha=0.4)
            fig.tight_layout(pad=1.0)
            canvas = FigureCanvasTkAgg(fig, master=shadow_frame)
            canvas.get_tk_widget().pack(padx=15, pady=10)
            state["bars"] = list(bars)
            state["canvas"] = canvas

            # Controls
            def calibrate_dark():
                # Use last seen raw values as baseline if available
                buf = self._as7341_buf.get("data", {})
                if buf:
                    state["baseline"] = {
                        k: float(buf.get(k, 0.0))
                        for k in [
                            "F1",
                            "F2",
                            "F3",
                            "F4",
                            "F5",
                            "F6",
                            "F7",
                            "F8",
                            "CLEAR",
                            "NIR",
                        ]
                    }

            tb.Button(
                shadow_frame,
                text="Calibrate (Dark)",
                command=calibrate_dark,
                bootstyle="secondary",
            ).pack(pady=10, padx=15)
        # else: future sensor types

    def build_dht_plot(self, parent=None, compact=False, sensor_name=None):
        import matplotlib

        matplotlib.rcParams.update(
            {
                "axes.titlesize": 14,
                "axes.titleweight": "bold",
                "axes.labelsize": 12,
                "axes.labelweight": "bold",
                "xtick.labelsize": 10,
                "ytick.labelsize": 10,
                "legend.fontsize": 10,
                "legend.frameon": True,
                "legend.loc": "upper right",
                "axes.grid": True,
                "grid.alpha": 0.3,
                "axes.facecolor": "#f8f9fa",
                "figure.facecolor": "#f8f9fa",
                "axes.edgecolor": "#22262A",
                "axes.linewidth": 1.2,
            }
        )
        # If called from Sensors page, parent is provided
        if parent is None:
            parent = self.tab_sensors
        # Clear previous
        for w in parent.winfo_children():
            if hasattr(w, "is_sensor_graph"):
                w.destroy()
        card = tb.Frame(parent, bootstyle="light", borderwidth=1, relief="solid")
        card.is_sensor_graph = True
        card.pack(side=LEFT, padx=10, pady=10, fill=None, expand=False)
        self.fig = Figure(figsize=(4, 2.5) if compact else (6, 4), dpi=100)
        self.ax1 = self.fig.add_subplot(111)
        # Plot data: only two lines, red for temp, blue for humidity
        show_temp = getattr(self, "_show_temp", True)
        show_hum = getattr(self, "_show_hum", True)
        temp_color = getattr(self, "_temp_color", "#d62728")  # Red
        hum_color = getattr(self, "_hum_color", "#1f77b4")  # Blue
        temp_ylim = getattr(self, "_temp_ylim", (0, 50))
        hum_ylim = getattr(self, "_hum_ylim", (0, 100))
        if self.is_connected and self.time_data:
            import pandas as pd

            temp_series = pd.Series(self.temp_data)
            hum_series = pd.Series(self.hum_data)
            if len(self.time_data) > 10:
                temp_smooth = temp_series.rolling(window=5, min_periods=1).mean()
                hum_smooth = hum_series.rolling(window=5, min_periods=1).mean()
            else:
                temp_smooth = temp_series
                hum_smooth = hum_series
            lines = []
            labels = []
            if show_temp:
                (l1,) = self.ax1.plot(
                    self.time_data,
                    temp_smooth,
                    color=temp_color,
                    label="Temperature (°C)",
                    marker="o",
                    markersize=4,
                    linewidth=2,
                )
                lines.append(l1)
                labels.append("Temperature (°C)")
            if show_hum:
                (l2,) = self.ax1.plot(
                    self.time_data,
                    hum_smooth,
                    color=hum_color,
                    label="Humidity (%)",
                    marker="s",
                    markersize=4,
                    linewidth=2,
                )
                lines.append(l2)
                labels.append("Humidity (%)")
            self.ax1.set_xlabel("Time (s)", fontweight="bold")
            # Set y-axis limits and label
            if show_temp and not show_hum:
                self.ax1.set_ylabel("Temperature (°C)", fontweight="bold")
                self.ax1.set_ylim(*temp_ylim)
            elif show_hum and not show_temp:
                self.ax1.set_ylabel("Humidity (%)", fontweight="bold")
                self.ax1.set_ylim(*hum_ylim)
        else:
            self.ax1.set_ylabel("Value", fontweight="bold")
            self.ax1.set_ylim(
                min(temp_ylim[0], hum_ylim[0]), max(temp_ylim[1], hum_ylim[1])
            )
        self.ax1.legend(
            lines,
            labels,
            loc="upper right",
            frameon=True,
            fancybox=True,
            borderpad=1,
        )
        if not self.is_connected or not self.time_data:
            self.ax1.set_title("No data", fontweight="bold")
        # Set the plot title to the sensor's name if provided
        if sensor_name:
            self.ax1.set_title(sensor_name, fontweight="bold")
        self.ax1.grid(True, linestyle="--", alpha=0.4)
        self.fig.tight_layout(pad=2.0)
        for spine in self.ax1.spines.values():
            spine.set_edgecolor("#22262A")
            spine.set_linewidth(1.2)
        if hasattr(self, "canvas"):
            self.canvas.get_tk_widget().destroy()
        self.canvas = FigureCanvasTkAgg(self.fig, master=card)
        self.canvas.get_tk_widget().pack(padx=10, pady=10)

        # Add a Graph Settings button for customization
        def open_graph_settings():
            popup = tk.Toplevel(self)
            popup.title("Graph Settings")
            popup.geometry("320x260")
            popup.resizable(False, False)
            tb.Label(
                popup,
                text="Graph Settings",
                font=("Segoe UI", 13, "bold"),
                bootstyle="info",
            ).pack(pady=10)
            # Show/hide lines
            temp_var = tk.BooleanVar(value=show_temp)
            hum_var = tk.BooleanVar(value=show_hum)
            tb.Checkbutton(
                popup, text="Show Temperature (Red)", variable=temp_var
            ).pack(anchor="w", padx=20)
            tb.Checkbutton(popup, text="Show Humidity (Blue)", variable=hum_var).pack(
                anchor="w", padx=20
            )
            # Axis limits
            tb.Label(popup, text="Temperature Y-Axis (°C):").pack(
                anchor="w", padx=20, pady=(10, 0)
            )
            temp_min = tk.DoubleVar(value=temp_ylim[0])
            temp_max = tk.DoubleVar(value=temp_ylim[1])
            tb.Entry(popup, textvariable=temp_min, width=6).pack(
                side=LEFT, padx=(20, 2)
            )
            tb.Label(popup, text="to").pack(side=LEFT)
            tb.Entry(popup, textvariable=temp_max, width=6).pack(side=LEFT, padx=(2, 0))
            tb.Label(popup, text="").pack(side=LEFT, padx=10)
            tb.Label(popup, text="Humidity Y-Axis (%):").pack(
                anchor="w", padx=20, pady=(10, 0)
            )
            hum_min = tk.DoubleVar(value=hum_ylim[0])
            hum_max = tk.DoubleVar(value=hum_ylim[1])
            tb.Entry(popup, textvariable=hum_min, width=6).pack(side=LEFT, padx=(20, 2))
            tb.Label(popup, text="to").pack(side=LEFT)
            tb.Entry(popup, textvariable=hum_max, width=6).pack(side=LEFT, padx=(2, 0))

            def save_settings():
                self._show_temp = temp_var.get()
                self._show_hum = hum_var.get()
                self._temp_ylim = (temp_min.get(), temp_max.get())
                self._hum_ylim = (hum_min.get(), hum_max.get())
                popup.destroy()
                self.build_sensors_tab()

            tb.Button(
                popup, text="Save", command=save_settings, bootstyle="success"
            ).pack(pady=20)

        tb.Button(
            card,
            text="Graph Settings",
            command=open_graph_settings,
            bootstyle="info-outline",
        ).pack(pady=(0, 10))

    def build_3d_plot(self, parent=None, compact=False):
        if parent is None:
            parent = self.tab_sensors
        for w in parent.winfo_children():
            if hasattr(w, "is_sensor_graph"):
                w.destroy()
        card = tb.Frame(parent, bootstyle="light", borderwidth=1, relief="solid")
        card.is_sensor_graph = True
        card.pack(side=LEFT, padx=10, pady=10, fill=None, expand=False)
        fig3d = Figure(figsize=(3, 2) if compact else (5, 4), dpi=100)
        self.ax3d = fig3d.add_subplot(111, projection="3d")
        self.ax3d.set_xlim([-1, 1])
        self.ax3d.set_ylim([-1, 1])
        self.ax3d.set_zlim([-1, 1])
        self.ax3d.set_title("3D Orientation")
        self.cube_data = self.make_cube()
        self.plot_cube(*self.cube_data)
        self.canvas3d = FigureCanvasTkAgg(fig3d, master=card)
        self.canvas3d.draw()
        self.canvas3d.get_tk_widget().pack()

    def make_cube(self, size=0.5):
        """
        Generate the coordinates for a cube of the given size.
        """
        r = [-size, size]
        x, y, z = np.meshgrid(r, r, r)
        return np.array([x.flatten(), y.flatten(), z.flatten()])

    def plot_cube(self, x, y, z):
        """
        Plot a cube in the 3D orientation plot.
        """
        self.ax3d.cla()
        self.ax3d.set_xlim([-1, 1])
        self.ax3d.set_ylim([-1, 1])
        self.ax3d.set_zlim([-1, 1])
        self.ax3d.set_title("3D Orientation")
        self.ax3d.scatter(x, y, z, color="skyblue")
        for i in range(8):
            for j in range(i + 1, 8):
                if (
                    np.sum(
                        np.abs(
                            np.array([x[i], y[i], z[i]]) - np.array([x[j], y[j], z[j]])
                        )
                    )
                    == 1.0
                ):
                    self.ax3d.plot(
                        [x[i], x[j]], [y[i], y[j]], [z[i], z[j]], color="blue"
                    )

    def _create_3d_orientation_for_data_tab(self, parent):
        """Create 3D orientation plot specifically for the data management tab"""
        try:
            # Create figure for data tab
            fig3d = Figure(figsize=(6, 4), dpi=100)
            self.ax3d_data = fig3d.add_subplot(111, projection="3d")
            self.ax3d_data.set_xlim([-1, 1])
            self.ax3d_data.set_ylim([-1, 1])
            self.ax3d_data.set_zlim([-1, 1])
            self.ax3d_data.set_title("3D Orientation - Live MPU Data")

            # Initialize cube data for data tab
            self.cube_data_data_tab = self.make_cube()
            self.plot_cube_data_tab(*self.cube_data_data_tab)

            # Create canvas for data tab
            self.canvas3d_data = FigureCanvasTkAgg(fig3d, master=parent)
            self.canvas3d_data.draw()
            self.canvas3d_data.get_tk_widget().pack(fill=BOTH, expand=True)

        except Exception as e:
            print(f"[ERROR] Failed to create 3D orientation for data tab: {e}")

    def plot_cube_data_tab(self, x, y, z):
        """Plot cube specifically for data tab 3D orientation"""
        try:
            self.ax3d_data.cla()
            self.ax3d_data.set_xlim([-1, 1])
            self.ax3d_data.set_ylim([-1, 1])
            self.ax3d_data.set_zlim([-1, 1])
            self.ax3d_data.set_title("3D Orientation - Live MPU Data")
            self.ax3d_data.scatter(x, y, z, color="skyblue", s=50)

            # Draw cube edges
            for i in range(8):
                for j in range(i + 1, 8):
                    if (
                        np.linalg.norm(
                            np.array([x[i], y[i], z[i]]) - np.array([x[j], y[j], z[j]])
                        )
                        == 1.0
                    ):
                        self.ax3d_data.plot(
                            [x[i], x[j]],
                            [y[i], y[j]],
                            [z[i], z[j]],
                            color="blue",
                            linewidth=2,
                        )
        except Exception as e:
            print(f"[ERROR] Failed to plot cube in data tab: {e}")

    def update_3d_orientation(self):
        """
        Update the 3D orientation plot based on the latest sensor data.
        """
        try:
            if not hasattr(self, "cube_data") or not hasattr(self, "ax3d"):
                print("[WARNING] 3D plot not initialized, skipping update")
                return

            yaw = radians(self.yaw - self.cal_yaw)
            pitch = radians(self.pitch - self.cal_pitch)
            roll = radians(self.roll - self.cal_roll)

            Rz = np.array(
                [[cos(yaw), -sin(yaw), 0], [sin(yaw), cos(yaw), 0], [0, 0, 1]]
            )
            Ry = np.array(
                [[cos(pitch), 0, sin(pitch)], [0, 1, 0], [-sin(pitch), 0, cos(pitch)]]
            )
            Rx = np.array(
                [[1, 0, 0], [0, cos(roll), -sin(roll)], [0, sin(roll), cos(roll)]]
            )

            rotated = Rz @ Ry @ Rx @ self.cube_data
            self.plot_cube(rotated[0], rotated[1], rotated[2])
            if hasattr(self, "canvas3d"):
                self.canvas3d.draw()

            # Also update data tab 3D orientation if it exists
            if hasattr(self, "cube_data_data_tab") and hasattr(self, "ax3d_data"):
                rotated_data_tab = Rz @ Ry @ Rx @ self.cube_data_data_tab
                self.plot_cube_data_tab(
                    rotated_data_tab[0], rotated_data_tab[1], rotated_data_tab[2]
                )
                if hasattr(self, "canvas3d_data"):
                    self.canvas3d_data.draw()

        except Exception as e:
            print(f"[ERROR] 3D orientation update failed: {e}")

    def schedule_simulation(self):
        # Avoid extra UI refresh when connected; rely on data-driven updates
        if self.is_connected:
            self.after_job = self.after(1000, self.schedule_simulation)
            return
            # If not connected, keep plots alive but minimal
            self.update_dht_plot()
        self.after_job = self.after(1000, self.schedule_simulation)

    def _load_templates_if_needed(self):
        if self._template_cache is None:
            try:
                with open("sensor_templates.json", "r") as f:
                    templates = json.load(f)
                # precompile
                for t in templates:
                    rx = t.get("parser", {}).get("regex", "")
                    t["_compiled"] = re.compile(rx) if rx else None
                # map by type
                self._template_cache = {t["type"].upper(): t for t in templates}
            except Exception:
                self._template_cache = {}
        return self._template_cache

    def _get_template_by_type(self, type_str):
        cache = self._load_templates_if_needed()
        return cache.get(type_str.upper())

    def open_add_sensor_dialog(self):
        # Dialog for adding a sensor
        popup = tk.Toplevel(self)
        popup.title("Add Sensor")
        popup.geometry("350x260")
        popup.resizable(False, False)
        tb.Label(
            popup, text="Add Sensor", font=("Segoe UI", 14, "bold"), bootstyle="info"
        ).pack(pady=10)
        tb.Label(popup, text="Type:").pack()
        # Load types from templates lazily
        tpl = self._load_templates_if_needed()
        type_var = tk.StringVar(value=(list(tpl.keys())[0] if tpl else "DHT11"))
        type_menu = tb.Combobox(
            popup,
            textvariable=type_var,
            values=list(tpl.keys()) if tpl else ["DHT11", "MPU6050"],
            state="readonly",
        )
        type_menu.pack(pady=2)
        tb.Label(popup, text="Name:").pack()
        name_var = tk.StringVar()
        name_entry = tb.Entry(popup, textvariable=name_var)
        name_entry.pack(pady=2)
        name_entry.focus()
        tb.Label(popup, text="Port:").pack()
        port_var = tk.StringVar()
        port_menu = tb.Combobox(
            popup,
            textvariable=port_var,
            values=[p.device for p in serial.tools.list_ports.comports()],
            state="readonly",
        )
        port_menu.pack(pady=2)
        btn_frame = tb.Frame(popup)
        btn_frame.pack(side="bottom", fill=X, pady=15)

        def add():
            s_type = type_var.get().strip()
            s_name = name_var.get().strip() or s_type
            s_port = port_var.get().strip()
            t = self._get_template_by_type(s_type) or {}
            self.active_sensors.append(
                {
                    "type": s_type,
                    "name": s_name,
                    "port": s_port,
                    "icon": t.get("icon", "🧩"),
                    "fields": t.get("fields", []),
                    "graph": t.get("graph_type", "single-line"),
                    "_compiled": t.get("_compiled"),
                    "_labels": t.get("labels", {}),
                    "_ranges": t.get("ranges", {}),
                }
            )
            # init stream buffers for non-DHT/IMU
            if s_name not in self.generic_streams:
                self.generic_streams[s_name] = {"time": []}
                for f in t.get("fields", []):
                    self.generic_streams[s_name][f] = []
            self.build_sensors_tab()
            popup.destroy()

        tb.Button(btn_frame, text="Save", command=add, bootstyle="success").pack(
            side=LEFT, padx=5
        )

    def build_settings_tab(self):
        for w in self.tab_settings.winfo_children():
            w.destroy()
        tb.Label(
            self.tab_settings, text="Settings", font=("Segoe UI", 16, "bold")
        ).pack(pady=20)
        # Board name management
        boards_frame = tb.Frame(self.tab_settings)
        boards_frame.pack(pady=10)
        tb.Label(
            boards_frame, text="Saved Boards:", font=("Segoe UI", 12, "bold")
        ).pack(anchor="w")
        for port, name in self.board_names.items():
            row = tb.Frame(boards_frame)
            row.pack(fill=X, pady=2)
            tb.Label(row, text=f"{name} ({port})", font=("Segoe UI", 11)).pack(
                side=LEFT, padx=5
            )
            tb.Button(
                row,
                text="Edit",
                command=lambda p=port: self.edit_board_name(p),
                bootstyle="info-outline",
            ).pack(side=RIGHT, padx=5)
            tb.Button(
                row,
                text="Remove",
                command=lambda p=port: self.remove_board_name(p),
                bootstyle="danger-outline",
            ).pack(side=RIGHT, padx=5)

    def edit_board_name(self, port):
        def save_edit():
            new_name = name_var.get().strip()
            if new_name:
                self.board_names[port] = new_name
                self.save_board_names()
                self.refresh_ports()
                self.build_settings_tab()
            popup.destroy()

        popup = tk.Toplevel(self)
        popup.title("Edit Board Name")
        popup.geometry("300x120")
        tb.Label(
            popup, text=f"Edit name for {port}", font=("Segoe UI", 12, "bold")
        ).pack(pady=10)
        name_var = tk.StringVar(value=self.board_names.get(port, ""))
        entry = tb.Entry(popup, textvariable=name_var)
        entry.pack(pady=5)
        entry.focus()
        tb.Button(popup, text="Save", command=save_edit, bootstyle="success").pack(
            pady=5
        )

    def remove_board_name(self, port):
        if port in self.board_names:
            del self.board_names[port]
            self.save_board_names()
            self.refresh_ports()
            self.build_settings_tab()

    def prompt_name_board(self, port):
        def save_name():
            name = name_var.get().strip()
            if name:
                self.board_names[port] = name
                self.save_board_names()
                self.refresh_ports()
            popup.destroy()

        popup = tk.Toplevel(self)
        popup.title("Name This Board")
        popup.geometry("300x120")
        tb.Label(popup, text=f"Name for {port}", font=("Segoe UI", 12, "bold")).pack(
            pady=10
        )
        name_var = tk.StringVar()
        entry = tb.Entry(popup, textvariable=name_var)
        entry.pack(pady=5)
        entry.focus()
        tb.Button(popup, text="Save", command=save_name, bootstyle="success").pack(
            pady=5
        )

    def build_about_tab(self):
        for w in self.tab_about.winfo_children():
            w.destroy()

        # Main container with scrollable content
        main_frame = tb.Frame(self.tab_about)
        main_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        # Application header
        header_frame = tb.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 20))

        # App logo/icon area
        logo_frame = tb.Frame(header_frame)
        logo_frame.pack(side=LEFT, padx=(0, 20))

        # Create a simple logo placeholder
        logo_label = tb.Label(
            logo_frame, text="🌊", font=("Segoe UI", 48), bootstyle="info"
        )
        logo_label.pack()

        # App info
        info_frame = tb.Frame(header_frame)
        info_frame.pack(side=LEFT, fill=BOTH, expand=True)

        tb.Label(
            info_frame,
            text=APP_NAME,
            font=("Segoe UI", 24, "bold"),
            bootstyle="primary",
        ).pack(anchor="w")

        tb.Label(
            info_frame,
            text=f"Version {APP_VERSION}",
            font=("Segoe UI", 14),
            bootstyle="secondary",
        ).pack(anchor="w", pady=(5, 0))

        tb.Label(
            info_frame, text=APP_DESCRIPTION, font=("Segoe UI", 12), bootstyle="info"
        ).pack(anchor="w", pady=(10, 0))

        # Features section
        features_frame = tb.LabelFrame(
            main_frame, text="Key Features", bootstyle="info"
        )
        features_frame.pack(fill=X, pady=(0, 20))

        features = [
            "🔌 Real-time Serial Communication with Arduino/microcontrollers",
            "📊 Advanced Data Visualization with Interactive Charts",
            "🤖 AI-Powered Data Analysis with GPT4All Integration",
            "📈 Professional Statistical Analysis Tools",
            "💾 Data Export and Reporting Capabilities",
            "🎨 Modern, Professional User Interface",
            "⚡ High-Performance Real-time Processing",
            "🔧 Comprehensive Sensor Support (DHT, MPU6050, TDS, AS7341, etc.)",
        ]

        for feature in features:
            tb.Label(
                features_frame,
                text=feature,
                font=("Segoe UI", 10),
                bootstyle="secondary",
            ).pack(anchor="w", padx=10, pady=2)

        # Technical info
        tech_frame = tb.LabelFrame(
            main_frame, text="Technical Information", bootstyle="success"
        )
        tech_frame.pack(fill=X, pady=(0, 20))

        tech_info = [
            f"Python Version: {sys.version.split()[0]}",
            f"Platform: {sys.platform}",
            f"Architecture: {sys.maxsize > 2**32 and '64-bit' or '32-bit'}",
            f"Build Date: {datetime.now().strftime('%Y-%m-%d')}",
            f"AI Support: {'Enabled' if GPT4ALL_AVAILABLE else 'Disabled'}",
        ]

        for info in tech_info:
            tb.Label(
                tech_frame, text=info, font=("Consolas", 9), bootstyle="secondary"
            ).pack(anchor="w", padx=10, pady=1)

        # Company info
        company_frame = tb.LabelFrame(
            main_frame, text="Company Information", bootstyle="warning"
        )
        company_frame.pack(fill=X, pady=(0, 20))

        tb.Label(
            company_frame,
            text=f"Developed by {APP_AUTHOR}",
            font=("Segoe UI", 12, "bold"),
            bootstyle="warning",
        ).pack(anchor="w", padx=10, pady=5)

        tb.Label(
            company_frame,
            text=APP_COPYRIGHT,
            font=("Segoe UI", 10),
            bootstyle="secondary",
        ).pack(anchor="w", padx=10, pady=2)

        # Action buttons
        button_frame = tb.Frame(main_frame)
        button_frame.pack(fill=X, pady=(0, 20))

        tb.Button(
            button_frame,
            text="Visit Website",
            command=lambda: webbrowser.open(APP_WEBSITE),
            bootstyle="info-outline",
        ).pack(side=LEFT, padx=(0, 10))

        tb.Button(
            button_frame,
            text="View Logs",
            command=self.show_logs,
            bootstyle="secondary-outline",
        ).pack(side=LEFT, padx=(0, 10))

        tb.Button(
            button_frame,
            text="System Info",
            command=self.show_system_info,
            bootstyle="success-outline",
        ).pack(side=LEFT)

        # License info
        license_frame = tb.Frame(main_frame)
        license_frame.pack(fill=X)

        tb.Label(
            license_frame,
            text="This software is provided as-is for educational and professional use.\nPlease refer to the license agreement for terms and conditions.",
            font=("Segoe UI", 9),
            bootstyle="secondary",
            justify="center",
        ).pack()

    def show_logs(self):
        """Show application logs in a new window."""
        log_window = tk.Toplevel(self)
        log_window.title("Application Logs")
        log_window.geometry("800x600")

        # Create text widget with scrollbar
        text_frame = tb.Frame(log_window)
        text_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 9))
        scrollbar = tb.Scrollbar(
            text_frame, orient=tk.VERTICAL, command=text_widget.yview
        )
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Read and display log file
        try:
            if os.path.exists("sealink.log"):
                with open("sealink.log", "r", encoding="utf-8") as f:
                    log_content = f.read()
                    text_widget.insert(tk.END, log_content)
            else:
                text_widget.insert(
                    tk.END,
                    "No log file found. Logs will appear here as the application runs.",
                )
        except Exception as e:
            text_widget.insert(tk.END, f"Error reading log file: {e}")

        text_widget.config(state=tk.DISABLED)

        # Add refresh button
        button_frame = tb.Frame(log_window)
        button_frame.pack(fill=X, padx=10, pady=(0, 10))

        tb.Button(
            button_frame,
            text="Refresh",
            command=lambda: self.refresh_logs(text_widget),
            bootstyle="info-outline",
        ).pack(side=tk.LEFT)

        tb.Button(
            button_frame,
            text="Clear Logs",
            command=lambda: self.clear_logs(text_widget),
            bootstyle="danger-outline",
        ).pack(side=tk.LEFT, padx=(10, 0))

        tb.Button(
            button_frame,
            text="Export Logs",
            command=lambda: self.export_logs(),
            bootstyle="success-outline",
        ).pack(side=tk.RIGHT)

    def refresh_logs(self, text_widget):
        """Refresh the log display."""
        text_widget.config(state=tk.NORMAL)
        text_widget.delete(1.0, tk.END)

        try:
            if os.path.exists("sealink.log"):
                with open("sealink.log", "r", encoding="utf-8") as f:
                    log_content = f.read()
                    text_widget.insert(tk.END, log_content)
            else:
                text_widget.insert(tk.END, "No log file found.")
        except Exception as e:
            text_widget.insert(tk.END, f"Error reading log file: {e}")

        text_widget.config(state=tk.DISABLED)
        text_widget.see(tk.END)

    def clear_logs(self, text_widget):
        """Clear the log file and display."""
        if messagebox.askyesno(
            "Clear Logs", "Are you sure you want to clear all logs?"
        ):
            try:
                with open("sealink.log", "w", encoding="utf-8") as f:
                    f.write("")
                text_widget.config(state=tk.NORMAL)
                text_widget.delete(1.0, tk.END)
                text_widget.insert(tk.END, "Logs cleared.")
                text_widget.config(state=tk.DISABLED)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear logs: {e}")

    def export_logs(self):
        """Export logs to a file."""
        from tkinter import filedialog

        file = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt")],
            title="Export Logs",
        )
        if file:
            try:
                if os.path.exists("sealink.log"):
                    import shutil

                    shutil.copy("sealink.log", file)
                    messagebox.showinfo("Success", f"Logs exported to {file}")
                else:
                    messagebox.showwarning("Warning", "No log file found to export.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export logs: {e}")

    def show_system_info(self):
        """Show detailed system information."""
        info_window = tk.Toplevel(self)
        info_window.title("System Information")
        info_window.geometry("600x500")

        # Create text widget with scrollbar
        text_frame = tb.Frame(info_window)
        text_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 9))
        scrollbar = tb.Scrollbar(
            text_frame, orient=tk.VERTICAL, command=text_widget.yview
        )
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Gather system information
        import platform
        import psutil

        system_info = f"""
SYSTEM INFORMATION
{"=" * 50}

Application:
  Name: {APP_NAME}
  Version: {APP_VERSION}
  Build Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Python Environment:
  Python Version: {sys.version}
  Python Executable: {sys.executable}
  Platform: {sys.platform}
  Architecture: {platform.architecture()[0]}

Operating System:
  System: {platform.system()}
  Release: {platform.release()}
  Version: {platform.version()}
  Machine: {platform.machine()}
  Processor: {platform.processor()}

Hardware:
  CPU Count: {psutil.cpu_count()}
  CPU Usage: {psutil.cpu_percent()}%
  Memory Total: {psutil.virtual_memory().total / (1024**3):.1f} GB
  Memory Available: {psutil.virtual_memory().available / (1024**3):.1f} GB
  Memory Usage: {psutil.virtual_memory().percent}%
  Disk Usage: {psutil.disk_usage("/").percent}%

Dependencies:
  NumPy: {np.__version__}
  Pandas: {pd.__version__}
  Matplotlib: {plt.matplotlib.__version__}
  Tkinter: Available
  Serial: Available
  GPT4All: {"Available" if GPT4ALL_AVAILABLE else "Not Available"}

Application Status:
  Serial Ports: {len(serial.tools.list_ports.comports())} available
  AI Status: {getattr(self, "ai_mode", "Unknown")}
  Theme: {self.settings.get("theme", "Unknown")}
  Data Points: {len(self.data_log) if hasattr(self, "data_log") else 0}
"""

        text_widget.insert(tk.END, system_info)
        text_widget.config(state=tk.DISABLED)

    def show_settings(self):
        """
        Show the Settings dialog for theme, serial, and AI options.
        """
        settings = tk.Toplevel(self)
        settings.title("Settings")
        settings.geometry("420x320")
        settings.resizable(False, False)
        tb.Label(
            settings, text="Settings", font=("Segoe UI", 14, "bold"), bootstyle="info"
        ).pack(pady=10)

        # Theme selection
        theme_frame = tb.Frame(settings)
        theme_frame.pack(fill=X, padx=20, pady=5)
        tb.Label(theme_frame, text="Theme:").pack(side=LEFT)
        theme_var = tk.StringVar(value=self.settings.get("theme", "superhero"))
        theme_menu = tb.Combobox(
            theme_frame,
            textvariable=theme_var,
            values=["superhero", "flatly", "darkly", "cosmo", "morph", "pulse"],
            state="readonly",
        )
        theme_menu.pack(side=LEFT, padx=10)

        # Baud rate selection
        baud_frame = tb.Frame(settings)
        baud_frame.pack(fill=X, padx=20, pady=5)
        tb.Label(baud_frame, text="Baud Rate:").pack(side=LEFT)
        baud_var = tk.StringVar(value=str(self.settings.get("baud_rate", 9600)))
        baud_menu = tb.Combobox(
            baud_frame,
            textvariable=baud_var,
            values=["9600", "19200", "38400", "57600", "115200"],
            state="readonly",
        )
        baud_menu.pack(side=LEFT, padx=10)

        # AI Provider
        ai_frame = tb.Frame(settings)
        ai_frame.pack(fill=X, padx=20, pady=5)
        tb.Label(ai_frame, text="AI Provider:").pack(side=LEFT)
        ai_var = tk.StringVar(value=self.settings.get("ai_provider", "auto"))
        ai_menu = tb.Combobox(
            ai_frame,
            textvariable=ai_var,
            values=["auto", "openai", "gpt4all", "none"],
            state="readonly",
        )
        ai_menu.pack(side=LEFT, padx=10)

        # OpenAI API Key
        key_frame = tb.Frame(settings)
        key_frame.pack(fill=X, padx=20, pady=5)
        tb.Label(key_frame, text="OpenAI API Key:").pack(side=LEFT)
        key_var = tk.StringVar(value=self.settings.get("openai_api_key", ""))
        key_entry = tb.Entry(key_frame, textvariable=key_var, show="*")
        key_entry.pack(side=LEFT, padx=10, fill=X, expand=True)

        def save_settings():
            self.settings["theme"] = theme_var.get()
            self.settings["baud_rate"] = int(baud_var.get())
            self.settings["ai_provider"] = ai_var.get()
            self.settings["openai_api_key"] = key_var.get().strip()
            self.save_settings()
            # Apply theme immediately
            self.style.theme_use(self.settings["theme"])
            # Re-init AI
            self.init_ai()
            settings.destroy()
            self.status_lbl.config(text="Settings updated", bootstyle="success")
            self.after(
                2000,
                lambda: self.status_lbl.config(
                    text="Connected" if self.is_connected else "Disconnected",
                    bootstyle="success" if self.is_connected else "warning",
                ),
            )

        tb.Button(
            settings, text="Save", command=save_settings, bootstyle="success"
        ).pack(pady=15)

    def export_csv(self):
        """
        Export sensor data to a CSV file.
        """
        import csv
        from tkinter import filedialog

        file = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
        )
        if not file:
            return
        with open(file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Time (s)", "Temperature (C)", "Humidity (%)"])
            for t, temp, hum in zip(self.time_data, self.temp_data, self.hum_data):
                writer.writerow([t, temp, hum])
        self.show_notification("All data exported!", style="success")
        self.status_lbl.config(text="All data exported!", bootstyle="success")
        self.after(
            2000,
            lambda: self.status_lbl.config(
                text="Connected" if self.is_connected else "Disconnected",
                bootstyle="success" if self.is_connected else "warning",
            ),
        )

    def export_all_data(self):
        import csv
        from tkinter import filedialog

        file = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
        )
        if not file:
            return
        with open(file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Sensor", "Value1", "Value2", "Value3"])
            for entry in self.data_log:
                vals = list(entry["values"]) + ["", ""]
                writer.writerow(
                    [entry["timestamp"], entry["sensor"], vals[0], vals[1], vals[2]]
                )
        self.show_notification("All data exported!", style="success")

    def calculate_statistics(self):
        """Calculate statistical metrics for selected sensor data."""
        import numpy as np
        import pandas as pd
        from datetime import datetime

        selected_sensor = self.stats_sensor_var.get()

        if not self.data_log:
            self._update_stats_display("No data available for analysis.")
            return

        # Filter data by sensor if not "All Sensors"
        if selected_sensor != "All Sensors":
            filtered_data = [
                entry for entry in self.data_log if entry["sensor"] == selected_sensor
            ]
        else:
            filtered_data = self.data_log

        if not filtered_data:
            self._update_stats_display(f"No data found for sensor: {selected_sensor}")
            return

        # Convert to DataFrame for easier analysis
        df_data = []
        for entry in filtered_data:
            for i, value in enumerate(entry["values"]):
                if value is not None and value != "":
                    df_data.append(
                        {
                            "timestamp": entry["timestamp"],
                            "sensor": entry["sensor"],
                            "value": float(value),
                            "value_index": i,
                        }
                    )

        if not df_data:
            self._update_stats_display("No numeric data found for analysis.")
            return

        df = pd.DataFrame(df_data)

        # Calculate statistics
        stats_text = f"📊 STATISTICAL ANALYSIS REPORT\n"
        stats_text += f"{'=' * 50}\n"
        stats_text += f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        stats_text += f"Sensor: {selected_sensor}\n"
        stats_text += f"Total Data Points: {len(df)}\n"
        stats_text += (
            f"Time Range: {df['timestamp'].min()} to {df['timestamp'].max()}\n\n"
        )

        # Basic statistics
        stats_text += "📈 BASIC STATISTICS\n"
        stats_text += f"{'─' * 30}\n"
        stats_text += f"Mean:           {df['value'].mean():.4f}\n"
        stats_text += f"Median:         {df['value'].median():.4f}\n"
        stats_text += f"Standard Dev:   {df['value'].std():.4f}\n"
        stats_text += f"Variance:       {df['value'].var():.4f}\n"
        stats_text += f"Minimum:        {df['value'].min():.4f}\n"
        stats_text += f"Maximum:        {df['value'].max():.4f}\n"
        stats_text += f"Range:          {df['value'].max() - df['value'].min():.4f}\n\n"

        # Percentiles
        stats_text += "📊 PERCENTILES\n"
        stats_text += f"{'─' * 30}\n"
        stats_text += f"25th Percentile: {df['value'].quantile(0.25):.4f}\n"
        stats_text += f"50th Percentile: {df['value'].quantile(0.50):.4f}\n"
        stats_text += f"75th Percentile: {df['value'].quantile(0.75):.4f}\n"
        stats_text += f"90th Percentile: {df['value'].quantile(0.90):.4f}\n"
        stats_text += f"95th Percentile: {df['value'].quantile(0.95):.4f}\n\n"

        # Data quality
        stats_text += "🔍 DATA QUALITY\n"
        stats_text += f"{'─' * 30}\n"
        stats_text += f"Valid Values:    {len(df)}\n"
        stats_text += f"Missing Values:  {len(filtered_data) * 10 - len(df)}\n"
        stats_text += (
            f"Data Completeness: {(len(df) / (len(filtered_data) * 10)) * 100:.1f}%\n\n"
        )

        # Trend analysis
        if len(df) > 1:
            # Simple linear trend
            x = np.arange(len(df))
            y = df["value"].values
            slope, intercept = np.polyfit(x, y, 1)
            stats_text += "📈 TREND ANALYSIS\n"
            stats_text += f"{'─' * 30}\n"
            stats_text += f"Linear Trend:    {slope:.6f} units/point\n"
            stats_text += f"Trend Direction: {'Increasing' if slope > 0 else 'Decreasing' if slope < 0 else 'Stable'}\n"
            stats_text += f"Correlation:     {np.corrcoef(x, y)[0, 1]:.4f}\n\n"

        # Sensor-specific insights
        if selected_sensor == "Temperature":
            stats_text += "🌡️ TEMPERATURE INSIGHTS\n"
            stats_text += f"{'─' * 30}\n"
            if df["value"].mean() < 0:
                stats_text += "⚠️  Below freezing point\n"
            elif df["value"].mean() > 50:
                stats_text += "⚠️  High temperature detected\n"
            else:
                stats_text += "✅ Temperature within normal range\n"
        elif selected_sensor == "Humidity":
            stats_text += "💧 HUMIDITY INSIGHTS\n"
            stats_text += f"{'─' * 30}\n"
            if df["value"].mean() < 30:
                stats_text += "⚠️  Low humidity (dry conditions)\n"
            elif df["value"].mean() > 70:
                stats_text += "⚠️  High humidity (moist conditions)\n"
            else:
                stats_text += "✅ Humidity within comfortable range\n"
        elif selected_sensor == "TDS":
            stats_text += "💧 WATER QUALITY INSIGHTS\n"
            stats_text += f"{'─' * 30}\n"
            if df["value"].mean() < 50:
                stats_text += "✅ Excellent water quality (low TDS)\n"
            elif df["value"].mean() < 200:
                stats_text += "✅ Good water quality\n"
            elif df["value"].mean() < 500:
                stats_text += "⚠️  Fair water quality\n"
            else:
                stats_text += "⚠️  Poor water quality (high TDS)\n"

        self._update_stats_display(stats_text)

    def generate_data_report(self):
        """Generate a comprehensive data analysis report."""
        import pandas as pd
        from datetime import datetime
        from tkinter import filedialog

        if not self.data_log:
            self.show_notification(
                "No data available for report generation.", style="warning"
            )
            return

        # Ask user where to save the report
        file = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Save Data Analysis Report",
        )
        if not file:
            return

        # Generate comprehensive report
        report = f"SENSOR DATA ANALYSIS REPORT\n"
        report += f"{'=' * 60}\n"
        report += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"Total Data Entries: {len(self.data_log)}\n\n"

        # Sensor summary
        sensor_counts = {}
        for entry in self.data_log:
            sensor = entry["sensor"]
            sensor_counts[sensor] = sensor_counts.get(sensor, 0) + 1

        report += "SENSOR SUMMARY\n"
        report += f"{'─' * 30}\n"
        for sensor, count in sensor_counts.items():
            report += f"{sensor}: {count} entries\n"
        report += "\n"

        # Detailed analysis for each sensor
        for sensor in sensor_counts.keys():
            sensor_data = [
                entry for entry in self.data_log if entry["sensor"] == sensor
            ]
            if not sensor_data:
                continue

            report += f"DETAILED ANALYSIS: {sensor}\n"
            report += f"{'─' * 40}\n"

            # Extract numeric values
            values = []
            for entry in sensor_data:
                for value in entry["values"]:
                    if value is not None and value != "":
                        try:
                            values.append(float(value))
                        except:
                            pass

            if values:
                import numpy as np

                report += f"Data Points: {len(values)}\n"
                report += f"Mean: {np.mean(values):.4f}\n"
                report += f"Std Dev: {np.std(values):.4f}\n"
                report += f"Min: {np.min(values):.4f}\n"
                report += f"Max: {np.max(values):.4f}\n"
                report += f"Range: {np.max(values) - np.min(values):.4f}\n\n"
            else:
                report += "No numeric data available\n\n"

        # Save report with UTF-8 encoding
        with open(file, "w", encoding="utf-8") as f:
            f.write(report)

        self.show_notification(f"Data report saved to: {file}", style="success")

    def plot_data_trends(self):
        """Create trend plots for sensor data."""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import numpy as np

            if not self.data_log:
                self.show_notification(
                    "No data available for plotting.", style="warning"
                )
                return

            # Create a new window for plots
            plot_window = tk.Toplevel(self.root)
            plot_window.title("Sensor Data Trends")
            plot_window.geometry("800x600")

            # Get data for plotting
            sensors = list(set(entry["sensor"] for entry in self.data_log))

            # Create subplots
            fig, axes = plt.subplots(len(sensors), 1, figsize=(10, 6 * len(sensors)))
            if len(sensors) == 1:
                axes = [axes]

            for i, sensor in enumerate(sensors):
                sensor_data = [
                    entry for entry in self.data_log if entry["sensor"] == sensor
                ]

                # Extract time and values
                times = []
                values = []
                for entry in sensor_data:
                    for j, value in enumerate(entry["values"]):
                        if value is not None and value != "":
                            try:
                                times.append(j)  # Use index as time proxy
                                values.append(float(value))
                            except:
                                pass

                if values:
                    axes[i].plot(times, values, "b-", linewidth=2, label=sensor)
                    axes[i].set_title(f"{sensor} Trend Analysis")
                    axes[i].set_xlabel("Data Point Index")
                    axes[i].set_ylabel("Value")
                    axes[i].grid(True, alpha=0.3)
                    axes[i].legend()

                    # Add trend line
                    if len(values) > 1:
                        z = np.polyfit(times, values, 1)
                        p = np.poly1d(z)
                        axes[i].plot(times, p(times), "r--", alpha=0.8, label="Trend")

            plt.tight_layout()

            # Embed plot in tkinter window
            canvas = FigureCanvasTkAgg(fig, plot_window)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        except Exception as e:
            print(f"[ERROR] Plot generation failed: {e}")
            self.show_notification(f"Plot generation failed: {e}", style="danger")

    def advanced_data_analysis(self):
        """Perform advanced statistical analysis with visualizations."""
        try:
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import numpy as np
            import pandas as pd
            from scipy import stats

            if not self.data_log:
                self.show_notification(
                    "No data available for advanced analysis.", style="warning"
                )
                return

            # Create advanced analysis window
            analysis_window = tk.Toplevel(self.root)
            analysis_window.title("Advanced Data Analysis")
            analysis_window.geometry("1200x800")

            # Create notebook for different analysis types
            notebook = tb.Notebook(analysis_window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            # 1. Distribution Analysis Tab
            dist_frame = tb.Frame(notebook)
            notebook.add(dist_frame, text="Distributions")

            # Get all numeric data
            all_values = []
            sensor_values = {}
            for entry in self.data_log:
                sensor = entry["sensor"]
                if sensor not in sensor_values:
                    sensor_values[sensor] = []
                for value in entry["values"]:
                    if value is not None and value != "":
                        try:
                            val = float(value)
                            all_values.append(val)
                            sensor_values[sensor].append(val)
                        except:
                            pass

            if all_values:
                # Create distribution plots
                fig1, axes1 = plt.subplots(2, 2, figsize=(12, 8))
                fig1.suptitle("Data Distribution Analysis", fontsize=16)

                # Histogram
                axes1[0, 0].hist(
                    all_values, bins=30, alpha=0.7, color="blue", edgecolor="black"
                )
                axes1[0, 0].set_title("Overall Data Distribution")
                axes1[0, 0].set_xlabel("Value")
                axes1[0, 0].set_ylabel("Frequency")
                axes1[0, 0].grid(True, alpha=0.3)

                # Box plot by sensor
                sensor_data_for_box = [
                    sensor_values[sensor]
                    for sensor in sensor_values.keys()
                    if sensor_values[sensor]
                ]
                sensor_names = [
                    sensor for sensor in sensor_values.keys() if sensor_values[sensor]
                ]
                if sensor_data_for_box:
                    axes1[0, 1].boxplot(sensor_data_for_box, labels=sensor_names)
                    axes1[0, 1].set_title("Data Distribution by Sensor")
                    axes1[0, 1].set_ylabel("Value")
                    axes1[0, 1].tick_params(axis="x", rotation=45)
                    axes1[0, 1].grid(True, alpha=0.3)

                # Q-Q plot for normality
                stats.probplot(all_values, dist="norm", plot=axes1[1, 0])
                axes1[1, 0].set_title("Q-Q Plot (Normality Test)")
                axes1[1, 0].grid(True, alpha=0.3)

                # Cumulative distribution
                sorted_values = np.sort(all_values)
                cumulative = np.arange(1, len(sorted_values) + 1) / len(sorted_values)
                axes1[1, 1].plot(sorted_values, cumulative, "b-", linewidth=2)
                axes1[1, 1].set_title("Cumulative Distribution Function")
                axes1[1, 1].set_xlabel("Value")
                axes1[1, 1].set_ylabel("Cumulative Probability")
                axes1[1, 1].grid(True, alpha=0.3)

                plt.tight_layout()

                # Embed in tkinter
                canvas1 = FigureCanvasTkAgg(fig1, dist_frame)
                canvas1.draw()
                canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # 2. Correlation Analysis Tab
            corr_frame = tb.Frame(notebook)
            notebook.add(corr_frame, text="Correlations")

            # Create correlation matrix
            if len(sensor_values) > 1:
                # Create DataFrame for correlation analysis
                max_len = max(
                    len(sensor_values[sensor]) for sensor in sensor_values.keys()
                )
                corr_data = {}
                for sensor in sensor_values.keys():
                    values = sensor_values[sensor]
                    # Pad with NaN to make all arrays same length
                    padded_values = values + [np.nan] * (max_len - len(values))
                    corr_data[sensor] = padded_values

                df_corr = pd.DataFrame(corr_data)
                correlation_matrix = df_corr.corr()

                fig2, ax2 = plt.subplots(figsize=(10, 8))
                im = ax2.imshow(
                    correlation_matrix, cmap="coolwarm", aspect="auto", vmin=-1, vmax=1
                )
                ax2.set_xticks(range(len(correlation_matrix.columns)))
                ax2.set_yticks(range(len(correlation_matrix.columns)))
                ax2.set_xticklabels(correlation_matrix.columns, rotation=45)
                ax2.set_yticklabels(correlation_matrix.columns)
                ax2.set_title("Sensor Correlation Matrix")

                # Add correlation values to the plot
                for i in range(len(correlation_matrix.columns)):
                    for j in range(len(correlation_matrix.columns)):
                        text = ax2.text(
                            j,
                            i,
                            f"{correlation_matrix.iloc[i, j]:.2f}",
                            ha="center",
                            va="center",
                            color="black",
                            fontweight="bold",
                        )

                plt.colorbar(im, ax=ax2)
                plt.tight_layout()

                canvas2 = FigureCanvasTkAgg(fig2, corr_frame)
                canvas2.draw()
                canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # 3. Statistical Tests Tab
            tests_frame = tb.Frame(notebook)
            notebook.add(tests_frame, text="Statistical Tests")

            # Perform statistical tests
            tests_text = "📊 STATISTICAL TESTS RESULTS\n"
            tests_text += "=" * 50 + "\n\n"

            if all_values:
                # Normality test
                shapiro_stat, shapiro_p = stats.shapiro(
                    all_values[:5000]
                )  # Limit for performance
                tests_text += f"🔍 NORMALITY TEST (Shapiro-Wilk)\n"
                tests_text += f"{'─' * 30}\n"
                tests_text += f"Statistic: {shapiro_stat:.6f}\n"
                tests_text += f"P-value: {shapiro_p:.6f}\n"
                tests_text += f"Result: {'Data appears normal' if shapiro_p > 0.05 else 'Data is not normal'}\n\n"

                # Outlier detection using IQR
                Q1 = np.percentile(all_values, 25)
                Q3 = np.percentile(all_values, 75)
                IQR = Q3 - Q1
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                outliers = [x for x in all_values if x < lower_bound or x > upper_bound]

                tests_text += f"🎯 OUTLIER DETECTION (IQR Method)\n"
                tests_text += f"{'─' * 30}\n"
                tests_text += f"Q1: {Q1:.4f}\n"
                tests_text += f"Q3: {Q3:.4f}\n"
                tests_text += f"IQR: {IQR:.4f}\n"
                tests_text += f"Lower Bound: {lower_bound:.4f}\n"
                tests_text += f"Upper Bound: {upper_bound:.4f}\n"
                tests_text += f"Outliers Found: {len(outliers)}\n"
                tests_text += f"Outlier Percentage: {(len(outliers) / len(all_values) * 100):.2f}%\n\n"

                # Descriptive statistics
                tests_text += f"📈 DESCRIPTIVE STATISTICS\n"
                tests_text += f"{'─' * 30}\n"
                tests_text += f"Skewness: {stats.skew(all_values):.4f}\n"
                tests_text += f"Kurtosis: {stats.kurtosis(all_values):.4f}\n"
                tests_text += f"Mean: {np.mean(all_values):.4f}\n"
                tests_text += f"Median: {np.median(all_values):.4f}\n"
                tests_text += (
                    f"Mode: {stats.mode(all_values, keepdims=True)[0][0]:.4f}\n"
                )
                tests_text += f"Standard Error: {stats.sem(all_values):.4f}\n"

            # Display tests results
            tests_display = tk.Text(tests_frame, wrap=tk.WORD, font=("Consolas", 10))
            tests_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            tests_display.insert(tk.END, tests_text)
            tests_display.config(state=tk.DISABLED)

        except Exception as e:
            print(f"[ERROR] Advanced analysis failed: {e}")
            self.show_notification(f"Advanced analysis failed: {e}", style="danger")

    def export_filtered_csv(self):
        """Export filtered data to CSV based on selected sensor."""
        import csv
        from tkinter import filedialog

        selected_sensor = self.stats_sensor_var.get()

        if not self.data_log:
            self.show_notification("No data available for export.", style="warning")
            return

        # Filter data
        if selected_sensor != "All Sensors":
            filtered_data = [
                entry for entry in self.data_log if entry["sensor"] == selected_sensor
            ]
        else:
            filtered_data = self.data_log

        if not filtered_data:
            self.show_notification(
                f"No data found for sensor: {selected_sensor}", style="warning"
            )
            return

        # Ask user where to save
        file = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title=f"Export {selected_sensor} Data",
        )
        if not file:
            return

        # Export with enhanced format
        with open(file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Enhanced header
            writer.writerow(
                [
                    "Timestamp",
                    "Sensor",
                    "Value1",
                    "Value2",
                    "Value3",
                    "Value4",
                    "Value5",
                    "Value6",
                    "Value7",
                    "Value8",
                    "Value9",
                    "Value10",
                ]
            )

            for entry in filtered_data:
                vals = list(entry["values"])[:10]
                if len(vals) < 10:
                    vals += [""] * (10 - len(vals))
                writer.writerow([entry["timestamp"], entry["sensor"]] + vals)

        self.show_notification(f"Filtered data exported to: {file}", style="success")

    def toggle_recording(self):
        """Toggle data recording on/off."""
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        """Start recording data to CSV file."""
        from tkinter import filedialog
        from datetime import datetime

        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"sensor_data_{timestamp}.csv"

        file = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Save Recording As",
            initialvalue=default_filename,
        )
        if file:
            self.recording_path = file
            self.is_recording = True

            # Create the CSV file with headers
            try:
                import csv

                with open(file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "Timestamp",
                            "Sensor",
                            "Value1",
                            "Value2",
                            "Value3",
                            "Value4",
                            "Value5",
                            "Value6",
                            "Value7",
                            "Value8",
                            "Value9",
                            "Value10",
                        ]
                    )

                # Update UI
                self.record_button.config(
                    text="⏹️ Stop Recording", bootstyle="warning-outline"
                )
                self.rec_status_lbl.config(
                    text=f"🔴 Recording to: {file}", bootstyle="success"
                )
                logger.info(f"Started recording to: {file}")

            except Exception as e:
                messagebox.showerror(
                    "Recording Error", f"Failed to start recording: {e}"
                )
                logger.error(f"Failed to start recording: {e}")

    def stop_recording(self):
        """Stop recording data."""
        self.is_recording = False
        self.record_button.config(text="🔴 Start Recording", bootstyle="danger-outline")
        self.rec_status_lbl.config(text="⚪ Not Recording", bootstyle="secondary")
        logger.info("Stopped recording")

    def clear_data(self):
        """Clear all data from the table and log."""
        if messagebox.askyesno(
            "Clear Data",
            "Are you sure you want to clear all data? This action cannot be undone.",
        ):
            self.data_log.clear()
            # Clear the table
            for item in self.data_table.get_children():
                self.data_table.delete(item)
            # Update summary
            self.data_summary.config(text="Data Points: 0")
            logger.info("Data cleared by user")

    def _update_stats_display(self, text):
        """Update the statistics display text widget."""
        self.stats_display.config(state="normal")
        self.stats_display.delete(1.0, tk.END)
        self.stats_display.insert(1.0, text)
        self.stats_display.config(state="disabled")

    def show_tab(self, idx):
        for i, tab in enumerate(self.tabs):
            if i == idx:
                tab.lift()
            else:
                tab.lower()
        # Update dashboard quick stats and sensor list if on dashboard
        if idx == 0:
            self.build_dashboard()

    def show_notification(self, message, style="info"):
        if hasattr(self, "_notif") and self._notif.winfo_exists():
            self._notif.destroy()
        self._notif = tb.Label(
            self.topbar, text=message, bootstyle=style, font=("Segoe UI", 10, "bold")
        )
        self._notif.pack(side=RIGHT, padx=10)
        self.after(2000, self._notif.destroy)

    def build_dashboard(self):
        for w in self.tab_dashboard.winfo_children():
            w.destroy()
        # Modern, welcoming header
        header = tb.Frame(self.tab_dashboard, relief="ridge", borderwidth=1)
        header.pack(fill=X, pady=(20, 10))
        logo_img = Image.open("Sealielogo.png")
        logo_img = logo_img.resize((48, 48), Image.LANCZOS)
        logo_photo = ImageTk.PhotoImage(logo_img)
        logo_label = tk.Label(header, image=logo_photo)
        logo_label.image = logo_photo
        logo_label.pack(side=LEFT, padx=10)
        tb.Label(
            header,
            text="Welcome to Sealie Sense Dashboard!",
            font=("Segoe UI", 22, "bold"),
        ).pack(side=LEFT, padx=10)
        # Quick actions
        quick = tb.Frame(self.tab_dashboard)
        quick.pack(fill=X, pady=5)
        tb.Button(
            quick,
            text="Add Sensor",
            command=self.open_add_sensor_dialog,
            bootstyle="primary-outline",
        ).pack(side=LEFT, padx=5)
        tb.Button(
            quick,
            text="Serial Debug Log",
            command=self.show_serial_debug,
            bootstyle="info-outline",
        ).pack(side=LEFT, padx=5)
        tb.Button(
            quick,
            text="Export Data",
            command=self.export_all_data,
            bootstyle="success-outline",
        ).pack(side=LEFT, padx=5)
        # Modern meters/cards for each sensor (dashboard only)
        meters_frame = tb.Frame(self.tab_dashboard)
        meters_frame.pack(fill=X, pady=10)
        for sensor in self.active_sensors:
            meter_card = tb.Frame(
                meters_frame,
                bootstyle="light",
                borderwidth=2,
                relief="raised",
            )
            meter_card.pack(side=LEFT, padx=24, pady=5, fill=Y)
            tb.Label(
                meter_card,
                text=f"{sensor['icon']} {sensor['name']}",
                font=("Segoe UI", 13, "bold"),
            ).pack(pady=(0, 8))
            if sensor["type"] == "DHT" and (self.temp_data or self.hum_data):
                temp_val = self.temp_data[-1] if self.temp_data else 0
                hum_val = self.hum_data[-1] if self.hum_data else 0
                # Professional flat meters with color zones
                tb.Meter(
                    meter_card,
                    amountused=temp_val,
                    metertype="full",
                    subtext="Temp (°C)",
                    bootstyle="danger",
                    stripethickness=10,
                    interactive=False,
                    amounttotal=50,
                    textfont=("Segoe UI", 14, "bold"),
                    subtextfont=("Segoe UI", 10),
                    metersize=140,
                    showtext=True,
                    textright="°C",
                    arcrange=270,
                    arcoffset=135,
                    stepsize=1,
                    stripestyle="flat",
                ).pack(pady=8)
                tb.Meter(
                    meter_card,
                    amountused=hum_val,
                    metertype="full",
                    subtext="Humidity (%)",
                    bootstyle="info",
                    stripethickness=10,
                    interactive=False,
                    amounttotal=100,
                    textfont=("Segoe UI", 14, "bold"),
                    subtextfont=("Segoe UI", 10),
                    metersize=140,
                    showtext=True,
                    textright="%",
                    arcrange=270,
                    arcoffset=135,
                    stepsize=1,
                    stripestyle="flat",
                ).pack(pady=8)
            elif sensor["type"] == "IMU":
                tb.Meter(
                    meter_card,
                    amountused=self.yaw,
                    metertype="full",
                    subtext="Yaw (°)",
                    bootstyle="primary",
                    stripethickness=10,
                    interactive=False,
                    amounttotal=180,
                    textfont=("Segoe UI", 14, "bold"),
                    subtextfont=("Segoe UI", 10),
                    metersize=140,
                    showtext=True,
                    textright="°",
                    arcrange=270,
                    arcoffset=135,
                    stepsize=1,
                    stripestyle="flat",
                ).pack(pady=8)
                tb.Meter(
                    meter_card,
                    amountused=self.pitch,
                    metertype="full",
                    subtext="Pitch (°)",
                    bootstyle="warning",
                    stripethickness=10,
                    interactive=False,
                    amounttotal=90,
                    textfont=("Segoe UI", 14, "bold"),
                    subtextfont=("Segoe UI", 10),
                    metersize=140,
                    showtext=True,
                    textright="°",
                    arcrange=270,
                    arcoffset=135,
                    stepsize=1,
                    stripestyle="flat",
                ).pack(pady=8)
                tb.Meter(
                    meter_card,
                    amountused=self.roll,
                    metertype="full",
                    subtext="Roll (°)",
                    bootstyle="success",
                    stripethickness=10,
                    interactive=False,
                    amounttotal=180,
                    textfont=("Segoe UI", 14, "bold"),
                    subtextfont=("Segoe UI", 10),
                    metersize=140,
                    showtext=True,
                    textright="°",
                    arcrange=270,
                    arcoffset=135,
                    stepsize=1,
                    stripestyle="flat",
                ).pack(pady=8)
            else:
                tb.Label(
                    meter_card, text="No data", font=("Segoe UI", 11, "italic")
                ).pack(pady=8)
            tb.Button(
                meter_card,
                text="Configure",
                command=lambda s=sensor: self.configure_sensor(s),
                bootstyle="info-outline",
            ).pack(pady=5)
        # Quick stats
        stats_frame = tb.Frame(self.tab_dashboard)
        stats_frame.pack(pady=10)
        tb.Label(stats_frame, text="Quick Stats", font=("Segoe UI", 14, "bold")).pack(
            anchor="w"
        )
        self.quick_stats = tb.Label(
            stats_frame, text=self.get_quick_stats(), font=("Segoe UI", 12)
        )
        self.quick_stats.pack()
        # Live Sensor Meters - REPLACED Recent Activity
        meters_section = tb.LabelFrame(
            self.tab_dashboard, text="📊 Live Sensor Readings", bootstyle="info"
        )
        meters_section.pack(fill=BOTH, expand=True, pady=10)

        # Create meters container
        meters_container = tb.Frame(meters_section)
        meters_container.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Temperature meter
        if hasattr(self, "temp_data") and self.temp_data:
            temp_frame = tb.Frame(meters_container)
            temp_frame.pack(fill=X, pady=5)
            self._draw_enhanced_meter(
                temp_frame,
                "🌡️ Temperature",
                self.temp_data[-1] if self.temp_data else 0,
                -10,
                60,
                "#ff6b6b",
            )

        # Humidity meter
        if hasattr(self, "hum_data") and self.hum_data:
            hum_frame = tb.Frame(meters_container)
            hum_frame.pack(fill=X, pady=5)
            self._draw_enhanced_meter(
                hum_frame,
                "💧 Humidity",
                self.hum_data[-1] if self.hum_data else 0,
                0,
                100,
                "#4ecdc4",
            )

        # TDS meter
        if hasattr(self, "tds_data") and self.tds_data:
            tds_frame = tb.Frame(meters_container)
            tds_frame.pack(fill=X, pady=5)
            self._draw_enhanced_meter(
                tds_frame,
                "💧 Water Quality (TDS)",
                self.tds_data[-1] if self.tds_data else 0,
                0,
                1500,
                "#45b7d1",
            )

        # IMU orientation meters
        if hasattr(self, "yaw") and (
            self.yaw != 0 or self.pitch != 0 or self.roll != 0
        ):
            imu_frame = tb.Frame(meters_container)
            imu_frame.pack(fill=X, pady=5)

            # Yaw meter
            yaw_subframe = tb.Frame(imu_frame)
            yaw_subframe.pack(fill=X, pady=2)
            self._draw_enhanced_meter(
                yaw_subframe, "🧭 Yaw", self.yaw, -180, 180, "#96ceb4"
            )

            # Pitch meter
            pitch_subframe = tb.Frame(imu_frame)
            pitch_subframe.pack(fill=X, pady=2)
            self._draw_enhanced_meter(
                pitch_subframe, "📐 Pitch", self.pitch, -90, 90, "#feca57"
            )

            # Roll meter
            roll_subframe = tb.Frame(imu_frame)
            roll_subframe.pack(fill=X, pady=2)
            self._draw_enhanced_meter(
                roll_subframe, "🔄 Roll", self.roll, -180, 180, "#ff9ff3"
            )

        # No data message
        if not any(
            [
                hasattr(self, "temp_data") and self.temp_data,
                hasattr(self, "hum_data") and self.hum_data,
                hasattr(self, "tds_data") and self.tds_data,
                hasattr(self, "yaw")
                and (self.yaw != 0 or self.pitch != 0 or self.roll != 0),
            ]
        ):
            no_data_frame = tb.Frame(meters_container)
            no_data_frame.pack(fill=BOTH, expand=True)

            tb.Label(
                no_data_frame,
                text="📡 No sensor data available",
                font=("Segoe UI", 14, "italic"),
                bootstyle="secondary",
            ).pack(expand=True)

            tb.Label(
                no_data_frame,
                text="Connect a sensor to see live readings here",
                font=("Segoe UI", 10),
                bootstyle="muted",
            ).pack()

    def _draw_meter(self, parent, label, value, vmin, vmax, color):
        # Draw a compact meter (bar) for a value
        frame = tb.Frame(parent)
        frame.pack(pady=2, fill=X)
        tb.Label(frame, text=label, font=("Segoe UI", 9)).pack(side=LEFT)
        bar = tk.Canvas(frame, width=80, height=12, bg="#eee", highlightthickness=0)
        bar.pack(side=LEFT, padx=5)
        pct = (float(value) - vmin) / (vmax - vmin)
        pct = max(0, min(1, pct))
        bar.create_rectangle(0, 0, 80 * pct, 12, fill=color, outline="")
        tb.Label(frame, text=f"{value:.1f}", font=("Segoe UI", 9, "bold")).pack(
            side=LEFT, padx=2
        )

    def _draw_enhanced_meter(self, parent, label, value, vmin, vmax, color):
        """Draw an enhanced meter with better styling and status indicators"""
        frame = tb.Frame(parent)
        frame.pack(fill=X, pady=3)

        # Label and value
        label_frame = tb.Frame(frame)
        label_frame.pack(fill=X)

        tb.Label(label_frame, text=label, font=("Segoe UI", 11, "bold")).pack(side=LEFT)

        # Calculate percentage and status
        pct = (float(value) - vmin) / (vmax - vmin) if vmax != vmin else 0
        pct = max(0, min(1, pct))

        # Status indicator
        if pct < 0.3:
            status = "🟢 Low"
            status_color = "#28a745"
        elif pct < 0.7:
            status = "🟡 Normal"
            status_color = "#ffc107"
        else:
            status = "🔴 High"
            status_color = "#dc3545"

        tb.Label(
            label_frame,
            text=status,
            font=("Segoe UI", 9),
            bootstyle="success" if pct < 0.3 else "warning" if pct < 0.7 else "danger",
        ).pack(side=RIGHT)

        # Value display
        tb.Label(
            label_frame,
            text=f"{value:.2f}",
            font=("Segoe UI", 12, "bold"),
            bootstyle="primary",
        ).pack(side=RIGHT, padx=(0, 10))

        # Enhanced progress bar
        bar_frame = tb.Frame(frame)
        bar_frame.pack(fill=X, pady=(5, 0))

        # Background bar
        bg_bar = tk.Canvas(
            bar_frame,
            height=20,
            bg="#e9ecef" if not self.night_mode else "#2d3748",
            highlightthickness=0,
            relief="sunken",
            bd=1,
        )
        bg_bar.pack(fill=X)

        # Progress fill
        bar_width = bg_bar.winfo_reqwidth() if bg_bar.winfo_reqwidth() > 0 else 200
        fill_width = bar_width * pct

        # Create gradient effect
        for i in range(int(fill_width)):
            intensity = i / fill_width if fill_width > 0 else 0
            # Create color gradient
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)

            # Darken based on intensity
            r = int(r * (0.3 + 0.7 * intensity))
            g = int(g * (0.3 + 0.7 * intensity))
            b = int(b * (0.3 + 0.7 * intensity))

            gradient_color = f"#{r:02x}{g:02x}{b:02x}"
            bg_bar.create_rectangle(i, 0, i + 1, 20, fill=gradient_color, outline="")

        # Range labels
        range_frame = tb.Frame(frame)
        range_frame.pack(fill=X, pady=(2, 0))

        tb.Label(
            range_frame, text=f"{vmin}", font=("Segoe UI", 8), bootstyle="muted"
        ).pack(side=LEFT)

        tb.Label(
            range_frame, text=f"{vmax}", font=("Segoe UI", 8), bootstyle="muted"
        ).pack(side=RIGHT)

    def get_quick_stats(self):
        if self.time_data:
            return f"Temp: {self.temp_data[-1]:.1f}°C, Humidity: {self.hum_data[-1]:.1f}%, Yaw: {self.yaw:.1f}°"
        elif self.yaw != 0 or self.pitch != 0 or self.roll != 0:
            return f"Yaw: {self.yaw:.1f}°, Pitch: {self.pitch:.1f}°, Roll: {self.roll:.1f}°"
        else:
            return "No data yet. Connect a sensor."

    def build_data_tab(self):
        for w in self.tab_data.winfo_children():
            w.destroy()

        # Main container with padding
        main_container = tb.Frame(self.tab_data)
        main_container.pack(fill=BOTH, expand=True, padx=15, pady=15)

        # Header section with title and status
        header_frame = tb.Frame(main_container)
        header_frame.pack(fill=X, pady=(0, 15))

        # Title and status in a clean layout
        title_frame = tb.Frame(header_frame)
        title_frame.pack(fill=X)

        # Main title with icon
        title_label = tb.Label(
            title_frame,
            text="📊 Data Management",
            font=("Segoe UI", 18, "bold"),
            bootstyle="primary",
        )
        title_label.pack(side=LEFT)

        # Status indicator with better styling
        status_frame = tb.Frame(title_frame)
        status_frame.pack(side=RIGHT)

        rec_text = (
            f"🔴 Recording to: {getattr(self, 'recording_path', '')}"
            if self.is_recording
            else "⚪ Not Recording"
        )
        self.rec_status_lbl = tb.Label(
            status_frame,
            text=rec_text,
            font=("Segoe UI", 11),
            bootstyle="success" if self.is_recording else "secondary",
        )
        self.rec_status_lbl.pack(side=RIGHT)

        # Data controls section
        controls_frame = tb.LabelFrame(
            main_container, text="Data Controls", bootstyle="info"
        )
        controls_frame.pack(fill=X, pady=(0, 15))

        # Control buttons in a clean row
        control_buttons = tb.Frame(controls_frame)
        control_buttons.pack(fill=X, padx=10, pady=10)

        # Start/Stop recording button
        self.record_button = tb.Button(
            control_buttons,
            text="🔴 Start Recording" if not self.is_recording else "⏹️ Stop Recording",
            command=self.toggle_recording,
            bootstyle="danger-outline" if not self.is_recording else "warning-outline",
            width=15,
        )
        self.record_button.pack(side=LEFT, padx=(0, 10))

        # Clear data button
        tb.Button(
            control_buttons,
            text="🗑️ Clear Data",
            command=self.clear_data,
            bootstyle="warning-outline",
            width=15,
        ).pack(side=LEFT, padx=(0, 10))

        # Export button
        tb.Button(
            control_buttons,
            text="📤 Export All",
            command=self.export_all_data,
            bootstyle="success-outline",
            width=15,
        ).pack(side=LEFT, padx=(0, 10))

        # Data summary
        summary_frame = tb.Frame(control_buttons)
        summary_frame.pack(side=RIGHT)

        self.data_summary = tb.Label(
            summary_frame,
            text=f"Data Points: {len(self.data_log)}",
            font=("Segoe UI", 10),
            bootstyle="info",
        )
        self.data_summary.pack(side=RIGHT)

        # Enhanced data table section
        table_section = tb.LabelFrame(
            main_container, text="Sensor Data", bootstyle="success"
        )
        table_section.pack(fill=BOTH, expand=True, pady=(0, 15))

        # Table container with better styling
        table_container = tb.Frame(table_section)
        table_container.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Create enhanced Treeview
        columns = (
            "Timestamp",
            "Sensor",
            "Value1",
            "Value2",
            "Value3",
            "Value4",
            "Value5",
            "Value6",
            "Value7",
            "Value8",
            "Value9",
            "Value10",
        )

        self.data_table = tb.Treeview(
            table_container, columns=columns, show="headings", height=12
        )

        # Configure column headings with better widths
        column_widths = {
            "Timestamp": 150,
            "Sensor": 120,
            "Value1": 80,
            "Value2": 80,
            "Value3": 80,
            "Value4": 80,
            "Value5": 80,
            "Value6": 80,
            "Value7": 80,
            "Value8": 80,
            "Value9": 80,
            "Value10": 80,
        }

        for col in columns:
            self.data_table.heading(col, text=col, anchor="center")
            self.data_table.column(
                col, width=column_widths[col], minwidth=60, anchor="center"
            )

        # Enhanced scrollbars
        v_scrollbar = tb.Scrollbar(
            table_container,
            orient=VERTICAL,
            command=self.data_table.yview,
            bootstyle="primary",
        )
        h_scrollbar = tb.Scrollbar(
            table_container,
            orient=HORIZONTAL,
            command=self.data_table.xview,
            bootstyle="primary",
        )
        self.data_table.configure(
            yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set
        )

        # Pack with better layout
        self.data_table.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")

        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

        # Populate table with existing data
        for entry in self.data_log:
            vals = list(entry["values"])[:10]
            if len(vals) < 10:
                vals += [""] * (10 - len(vals))
            self.data_table.insert(
                "",
                "end",
                values=(entry["timestamp"], entry["sensor"], *vals),
            )
        # Statistical Analysis Tools - ENHANCED
        stats_frame = tb.LabelFrame(
            main_container, text="📈 Statistical Analysis Tools", bootstyle="warning"
        )
        stats_frame.pack(fill=BOTH, expand=True, pady=(0, 15))

        # Analysis controls with better layout
        stats_controls = tb.Frame(stats_frame)
        stats_controls.pack(fill=X, padx=10, pady=10)

        # First row - Sensor selection and basic stats
        row1 = tb.Frame(stats_controls)
        row1.pack(fill=X, pady=(0, 10))

        tb.Label(
            row1,
            text="Analyze Sensor:",
            font=("Segoe UI", 10, "bold"),
            bootstyle="primary",
        ).pack(side=LEFT, padx=(0, 5))
        self.stats_sensor_var = tk.StringVar(value="All Sensors")
        self.stats_sensor_combo = tb.Combobox(
            row1,
            textvariable=self.stats_sensor_var,
            values=[
                "All Sensors",
                "Temperature",
                "Humidity",
                "TDS",
                "MPU6050",
                "AS7341",
                "DS18B20",
            ],
            state="readonly",
            width=15,
            font=("Segoe UI", 10),
        )
        self.stats_sensor_combo.pack(side=LEFT, padx=(0, 20))

        # Basic statistics buttons
        basic_stats_frame = tb.Frame(row1)
        basic_stats_frame.pack(side=LEFT, padx=(0, 20))

        tb.Button(
            basic_stats_frame,
            text="📊 Basic Stats",
            command=self.calculate_statistics,
            bootstyle="success",
            width=12,
        ).pack(side=LEFT, padx=(0, 5))

        tb.Button(
            basic_stats_frame,
            text="📈 Trends",
            command=self.plot_data_trends,
            bootstyle="warning",
            width=12,
        ).pack(side=LEFT, padx=(0, 5))

        # Second row - Advanced analysis buttons
        row2 = tb.Frame(stats_controls)
        row2.pack(fill=X, pady=(0, 10))

        # Advanced analysis section
        advanced_frame = tb.Frame(row2)
        advanced_frame.pack(side=LEFT)

        tb.Label(
            advanced_frame, text="Advanced Analysis:", font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        advanced_buttons = tb.Frame(advanced_frame)
        advanced_buttons.pack(fill=X, pady=(5, 0))

        tb.Button(
            advanced_buttons,
            text="📋 Generate Report",
            command=self.generate_data_report,
            bootstyle="info",
            width=15,
        ).pack(side=LEFT, padx=(0, 5))

        tb.Button(
            advanced_buttons,
            text="🔍 Advanced Stats",
            command=self.advanced_data_analysis,
            bootstyle="danger",
            width=15,
        ).pack(side=LEFT, padx=(0, 5))

        tb.Button(
            advanced_buttons,
            text="📊 Correlation",
            command=self.calculate_correlations,
            bootstyle="primary",
            width=15,
        ).pack(side=LEFT, padx=(0, 5))

        tb.Button(
            advanced_buttons,
            text="📈 Regression",
            command=self.perform_regression,
            bootstyle="secondary",
            width=15,
        ).pack(side=LEFT, padx=(0, 5))

        # Third row - Export and utility buttons
        row3 = tb.Frame(stats_controls)
        row3.pack(fill=X)

        utility_frame = tb.Frame(row3)
        utility_frame.pack(side=LEFT)

        tb.Label(
            utility_frame, text="Export & Utilities:", font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        utility_buttons = tb.Frame(utility_frame)
        utility_buttons.pack(fill=X, pady=(5, 0))

        tb.Button(
            utility_buttons,
            text="📤 Export CSV",
            command=self.export_filtered_csv,
            bootstyle="success-outline",
            width=12,
        ).pack(side=LEFT, padx=(0, 5))

        tb.Button(
            utility_buttons,
            text="📊 Export Charts",
            command=self.export_charts,
            bootstyle="info-outline",
            width=12,
        ).pack(side=LEFT, padx=(0, 5))

        tb.Button(
            utility_buttons,
            text="🔄 Refresh Data",
            command=self.refresh_analysis_data,
            bootstyle="warning-outline",
            width=12,
        ).pack(side=LEFT, padx=(0, 5))

        # Statistics display area
        self.stats_display = tk.Text(
            stats_frame, height=8, state="disabled", wrap="word", font=("Consolas", 9)
        )
        self.stats_display.pack(fill=BOTH, expand=True, padx=10, pady=5)
        # AI Data Assistant (offline) - IMPROVED
        ai_frame = tb.LabelFrame(
            main_container, text="🤖 AI Data Assistant", bootstyle="info"
        )
        ai_frame.pack(fill=BOTH, expand=True, pady=(0, 10))

        # Chat display area with better styling
        chat_display_frame = tb.Frame(ai_frame)
        chat_display_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.ai_chat_log = tk.Text(
            chat_display_frame,
            height=8,
            state="disabled",
            wrap="word",
            font=("Consolas", 10),
            bg="#1e1e1e" if self.night_mode else "#ffffff",
            fg="#ffffff" if self.night_mode else "#000000",
            insertbackground="#ffffff" if self.night_mode else "#000000",
        )
        self.ai_chat_log.pack(fill=BOTH, expand=True)

        # Add scrollbar to chat log
        chat_scrollbar = tk.Scrollbar(
            chat_display_frame, orient="vertical", command=self.ai_chat_log.yview
        )
        chat_scrollbar.pack(side="right", fill="y")
        self.ai_chat_log.config(yscrollcommand=chat_scrollbar.set)

        # Ensure scrollbar doesn't interfere with entry widget
        chat_scrollbar.bind("<Button-1>", lambda e: "break")

        # Chat input area with better layout
        chat_input_frame = tb.Frame(ai_frame)
        chat_input_frame.pack(fill=X, padx=10, pady=(0, 10))

        # Input label with placeholder hint
        tb.Label(
            chat_input_frame,
            text="Ask about your data:",
            font=("Segoe UI", 10),
            bootstyle="secondary",
        ).pack(anchor="w", pady=(0, 2))

        # Placeholder hint
        tb.Label(
            chat_input_frame,
            text="💡 Try: 'What's the average temperature?' or 'Show me trends'",
            font=("Segoe UI", 8),
            bootstyle="muted",
        ).pack(anchor="w", pady=(0, 5))

        # Input row
        input_row = tb.Frame(chat_input_frame)
        input_row.pack(fill=X)

        # Simple working Entry widget
        self.ai_chat_entry = tk.Entry(
            input_row, font=("Segoe UI", 14), width=50, relief="solid", bd=2
        )
        self.ai_chat_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))

        # Ensure the entry widget can receive focus and input
        self.ai_chat_entry.bind(
            "<FocusIn>", lambda e: self.ai_chat_entry.config(state="normal")
        )
        self.ai_chat_entry.bind(
            "<KeyPress>", lambda e: self.ai_chat_entry.config(state="normal")
        )

        # Send button with better styling
        send_btn = tb.Button(
            input_row,
            text="Send",
            command=self.handle_ai_chat,
            bootstyle="primary",
            width=8,
        )
        send_btn.pack(side=RIGHT)

        # Bind Enter key to send message
        self.ai_chat_entry.bind("<Return>", lambda e: self.handle_ai_chat())

        # Additional bindings to ensure proper text input
        self.ai_chat_entry.bind("<Button-1>", lambda e: self.ai_chat_entry.focus_set())
        self.ai_chat_entry.bind(
            "<FocusIn>", lambda e: self.ai_chat_entry.config(state="normal")
        )

        # Force focus and ensure it's editable
        self.ai_chat_entry.focus_set()
        self.ai_chat_entry.config(state="normal")

        # Make sure the entry widget is properly configured for text input
        self.after(100, lambda: self.ai_chat_entry.focus_set())

    def handle_ai_chat(self):
        user_msg = self.ai_chat_entry.get().strip()
        if not user_msg:
            return
        self.ai_chat_entry.delete(0, tk.END)
        self.append_ai_chat(f"You: {user_msg}\n")
        # Route to selected AI provider (with fallback)
        reply = ""
        try:
            reply = self.ai_func(user_msg)
        except Exception as e:
            reply = f"AI error: {e}"
        self.append_ai_chat(f"AI ({self.ai_mode}): {reply}\n")

    def calculate_correlations(self):
        """Calculate correlations between different sensor readings"""
        try:
            df = self.get_data_df()
            if df.empty:
                self.show_notification(
                    "No data available for correlation analysis.", style="warning"
                )
                return

            # Select numeric columns only
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) < 2:
                self.show_notification(
                    "Need at least 2 numeric columns for correlation.", style="warning"
                )
                return

            # Calculate correlation matrix
            corr_matrix = df[numeric_cols].corr()

            # Display results
            self.stats_display.config(state="normal")
            self.stats_display.delete(1.0, tk.END)

            result = "📊 CORRELATION ANALYSIS\n"
            result += "=" * 50 + "\n\n"

            for i, col1 in enumerate(numeric_cols):
                for j, col2 in enumerate(numeric_cols):
                    if i < j:  # Only upper triangle
                        corr_val = corr_matrix.loc[col1, col2]
                        strength = (
                            "Strong"
                            if abs(corr_val) > 0.7
                            else "Moderate"
                            if abs(corr_val) > 0.3
                            else "Weak"
                        )
                        direction = "Positive" if corr_val > 0 else "Negative"

                        result += f"{col1} ↔ {col2}:\n"
                        result += f"  Correlation: {corr_val:.3f}\n"
                        result += f"  Strength: {strength} {direction}\n\n"

            self.stats_display.insert(tk.END, result)
            self.stats_display.config(state="disabled")

        except Exception as e:
            self.show_notification(f"Correlation analysis failed: {e}", style="danger")

    def perform_regression(self):
        """Perform simple linear regression analysis"""
        try:
            df = self.get_data_df()
            if df.empty:
                self.show_notification(
                    "No data available for regression analysis.", style="warning"
                )
                return

            numeric_cols = df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) < 2:
                self.show_notification(
                    "Need at least 2 numeric columns for regression.", style="warning"
                )
                return

            # Simple linear regression between first two numeric columns
            x_col, y_col = numeric_cols[0], numeric_cols[1]
            x_data = df[x_col].dropna()
            y_data = df[y_col].dropna()

            # Align data
            common_idx = x_data.index.intersection(y_data.index)
            x_vals = x_data.loc[common_idx].values
            y_vals = y_data.loc[common_idx].values

            if len(x_vals) < 3:
                self.show_notification(
                    "Not enough data points for regression.", style="warning"
                )
                return

            # Calculate regression coefficients
            n = len(x_vals)
            sum_x = np.sum(x_vals)
            sum_y = np.sum(y_vals)
            sum_xy = np.sum(x_vals * y_vals)
            sum_x2 = np.sum(x_vals**2)

            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2)
            intercept = (sum_y - slope * sum_x) / n

            # Calculate R-squared
            y_pred = slope * x_vals + intercept
            ss_res = np.sum((y_vals - y_pred) ** 2)
            ss_tot = np.sum((y_vals - np.mean(y_vals)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            # Display results
            self.stats_display.config(state="normal")
            self.stats_display.delete(1.0, tk.END)

            result = "📈 REGRESSION ANALYSIS\n"
            result += "=" * 50 + "\n\n"
            result += f"Predicting: {y_col} from {x_col}\n"
            result += f"Data points: {len(x_vals)}\n\n"
            result += f"Equation: {y_col} = {slope:.3f} × {x_col} + {intercept:.3f}\n"
            result += f"R-squared: {r_squared:.3f}\n"
            result += f"Slope: {slope:.3f}\n"
            result += f"Intercept: {intercept:.3f}\n\n"

            # Interpretation
            if r_squared > 0.7:
                result += "✅ Strong linear relationship\n"
            elif r_squared > 0.3:
                result += "⚠️ Moderate linear relationship\n"
            else:
                result += "❌ Weak linear relationship\n"

            self.stats_display.insert(tk.END, result)
            self.stats_display.config(state="disabled")

        except Exception as e:
            self.show_notification(f"Regression analysis failed: {e}", style="danger")

    def export_charts(self):
        """Export current charts and visualizations"""
        try:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Create charts directory
            charts_dir = "exported_charts"
            os.makedirs(charts_dir, exist_ok=True)

            # Export any active plots
            if hasattr(self, "current_plot_figure"):
                chart_path = os.path.join(charts_dir, f"sensor_chart_{timestamp}.png")
                self.current_plot_figure.savefig(
                    chart_path, dpi=300, bbox_inches="tight"
                )
                self.show_notification(
                    f"Chart exported to {chart_path}", style="success"
                )
            else:
                self.show_notification(
                    "No active charts to export. Generate a plot first.",
                    style="warning",
                )

        except Exception as e:
            self.show_notification(f"Chart export failed: {e}", style="danger")

    def refresh_analysis_data(self):
        """Refresh the analysis data and recalculate statistics"""
        try:
            # Rebuild the data tab to refresh all displays
            self.build_data_tab()
            self.show_notification(
                "Analysis data refreshed successfully", style="success"
            )
        except Exception as e:
            self.show_notification(f"Data refresh failed: {e}", style="danger")

    def append_ai_chat(self, msg):
        self.ai_chat_log.config(state="normal")
        self.ai_chat_log.insert(tk.END, msg)
        self.ai_chat_log.see(tk.END)
        self.ai_chat_log.config(state="disabled")

    def process_ai_query(self, query):
        # Offline rules-based parser for common stats/plots
        df = self.get_data_df()
        query_l = query.lower()
        try:
            if "mean" in query_l or "average" in query_l:
                if "temp" in query_l:
                    return f"Mean temperature: {df['Value1'].mean():.2f}"
                if "humidity" in query_l:
                    return f"Mean humidity: {df['Value2'].mean():.2f}"
                if "yaw" in query_l:
                    return f"Mean yaw: {df['Value1'][df['Sensor'] == '3D Orientation'].mean():.2f}"
                return f"Mean (Value1): {df['Value1'].mean():.2f}"
            if "std" in query_l or "standard deviation" in query_l:
                if "temp" in query_l:
                    return f"Std temperature: {df['Value1'].std():.2f}"
                if "humidity" in query_l:
                    return f"Std humidity: {df['Value2'].std():.2f}"
                return f"Std (Value1): {df['Value1'].std():.2f}"
            if "min" in query_l:
                if "temp" in query_l:
                    return f"Min temperature: {df['Value1'].min():.2f}"
                if "humidity" in query_l:
                    return f"Min humidity: {df['Value2'].min():.2f}"
                return f"Min (Value1): {df['Value1'].min():.2f}"
            if "max" in query_l:
                if "temp" in query_l:
                    return f"Max temperature: {df['Value1'].max():.2f}"
                if "humidity" in query_l:
                    return f"Max humidity: {df['Value2'].max():.2f}"
                return f"Max (Value1): {df['Value1'].max():.2f}"
            if "histogram" in query_l or "plot" in query_l:
                import matplotlib.pyplot as plt
                import tempfile
                import os

                if "temp" in query_l:
                    col = "Value1"
                    label = "Temperature"
                elif "humidity" in query_l:
                    col = "Value2"
                    label = "Humidity"
                else:
                    col = "Value1"
                    label = "Value1"
                fig, ax = plt.subplots()
                df[col].dropna().plot(kind="hist", ax=ax, bins=20, color="#304674")
                ax.set_title(f"Histogram of {label}")
                ax.set_xlabel(label)
                ax.set_ylabel("Frequency")
                tmpfile = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                fig.savefig(tmpfile.name)
                plt.close(fig)
                self.show_ai_image(tmpfile.name)
                os.unlink(tmpfile.name)
                return f"Histogram of {label} plotted."
            if "correlation" in query_l:
                corr = df.corr(numeric_only=True)
                return f"Correlation matrix:\n{corr.to_string()}"
            if "describe" in query_l or "summary" in query_l:
                desc = df.describe().to_string()
                return f"Summary statistics:\n{desc}"
            # Fallback: use local LLM if available
            if self.llm:
                response = self.llm.generate(query, max_tokens=200)
                return response.strip()
            return "Sorry, I couldn't understand your request. Try asking for mean, std, min, max, histogram, correlation, or summary."
        except Exception as e:
            return f"Error: {e}"

    def get_data_df(self):
        # Convert data_log to pandas DataFrame
        if not self.data_log:
            return pd.DataFrame(
                columns=["Timestamp", "Sensor", "Value1", "Value2", "Value3"]
            )
        rows = []
        for entry in self.data_log:
            vals = list(entry["values"]) + [None, None]
            rows.append(
                {
                    "Timestamp": entry["timestamp"],
                    "Sensor": entry["sensor"],
                    "Value1": vals[0],
                    "Value2": vals[1],
                    "Value3": vals[2],
                }
            )
        return pd.DataFrame(rows)

    def show_ai_image(self, img_path):
        # Show image in a popup window
        popup = tk.Toplevel(self)
        popup.title("AI Analysis Result")
        img = Image.open(img_path)
        img = img.resize((400, 300), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(popup, image=photo)
        label.image = photo
        label.pack()

    def _ensure_sidebar_content(self):
        """Rebuild the sidebar content if missing (after collapses or rebuilds)."""
        # Create container if missing
        if not hasattr(self, "sidebar_content") or self.sidebar_content is None:
            self.sidebar_content = tb.Frame(self.sidebar, bootstyle="dark")
            self.sidebar_content.pack(pady=(10, 0), fill=Y, expand=True)
        # If already has children, keep as is
        if self.sidebar_content.winfo_children():
            return
        # Logo and app name
        logo_frame = tb.Frame(self.sidebar_content, bootstyle="dark")
        logo_frame.pack(pady=(10, 10))
        try:
            logo_img = Image.open("Sealielogo.png").resize((48, 48), Image.LANCZOS)
            _photo = ImageTk.PhotoImage(logo_img)
            lbl = tk.Label(logo_frame, image=_photo)
            lbl.image = _photo
            lbl.pack()
        except Exception:
            tb.Label(logo_frame, text="SeaLink", font=("Segoe UI", 18, "bold")).pack()

        # Nav buttons
        def _btn(parent, text, cmd, tip):
            b = tb.Button(parent, text=text, command=cmd, bootstyle="dark")
            b.pack(fill=X, pady=8, padx=20)
            try:
                self.add_hover(b)
                self.create_tooltip(b, tip)
            except Exception:
                pass
            return b

        _btn(
            self.sidebar_content,
            "Dashboard",
            lambda: self.show_tab(0),
            "Show dashboard overview",
        )
        _btn(
            self.sidebar_content,
            "Sensors",
            lambda: self.show_tab(1),
            "View and manage sensors",
        )
        _btn(
            self.sidebar_content,
            "Data",
            lambda: self.show_tab(2),
            "View and export sensor data",
        )
        _btn(
            self.sidebar_content, "Settings", self.show_settings, "Open settings dialog"
        )
        _btn(self.sidebar_content, "About", lambda: self.show_tab(4), "About SeaLink")

    def toggle_sidebar(self, event=None):
        # Guard: sidebar may not be built yet
        if not hasattr(self, "sidebar") or self.sidebar is None:
            return
        if self.sidebar_expanded:
            # collapse: keep frame, shrink width and hide inner content
            try:
                if hasattr(self, "sidebar_content") and self.sidebar_content:
                    self.sidebar_content.pack_forget()
                self.sidebar.configure(width=self.sidebar_min_width)
                self.sidebar.pack_propagate(False)
            except Exception:
                pass
            self.sidebar_expanded = False
        else:
            # expand: restore width and (re)build content if needed
            try:
                self.sidebar.configure(width=180)
                self._ensure_sidebar_content()
                self.sidebar_content.pack(pady=(10, 0), fill=Y, expand=True)
                self.sidebar.pack(side=LEFT, fill=Y)
                self.sidebar.pack_propagate(False)
            except Exception:
                pass
            self.sidebar_expanded = True

    def drag_sidebar(self, event):
        # Allow user to drag to resize sidebar
        x = event.x_root - self.sidebar.winfo_rootx()
        new_width = max(self.sidebar_min_width, min(self.sidebar_max_width, x))
        self.sidebar.configure(width=new_width)
        if new_width > self.sidebar_min_width + 10:
            self.sidebar_content.pack(pady=(10, 0), fill=Y, expand=True)
            self.sidebar_expanded = True
        else:
            self.sidebar_content.pack_forget()
            self.sidebar_expanded = False

    def on_close(self):
        """
        Handle application close event: cleanup and exit.
        """
        self.is_connected = False
        if self.after_job:
            self.after_cancel(self.after_job)
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.destroy()

    def show_serial_debug(self):
        # Popup to show serial debug log
        popup = tk.Toplevel(self)
        popup.title("Serial Debug Log")
        popup.geometry("600x400")
        text = tk.Text(popup, state="normal")
        text.pack(fill=BOTH, expand=True)
        for line in getattr(self, "_serial_debug_log", []):
            text.insert(tk.END, line + "\n")
        text.config(state="disabled")

    def log_serial_debug(self, line):
        if not hasattr(self, "_serial_debug_log"):
            self._serial_debug_log = []
        self._serial_debug_log.append(line)
        # Keep last 200 lines
        self._serial_debug_log = self._serial_debug_log[-200:]

    def configure_sensor(self, sensor=None):
        # Dialog for configuring a sensor (port, name, etc.)
        popup = tk.Toplevel(self)
        popup.title("Configure Sensor")
        popup.geometry("350x220")
        tb.Label(
            popup,
            text="Configure Sensor",
            font=("Segoe UI", 14, "bold"),
            bootstyle="info",
        ).pack(pady=10)
        # Sensor type
        tb.Label(popup, text="Type:").pack()
        type_var = tk.StringVar(
            value=sensor["type"] if sensor else self.sensor_templates[0]["type"]
        )
        type_menu = tb.Combobox(
            popup,
            textvariable=type_var,
            values=[t["type"] for t in self.sensor_templates],
            state="readonly",
        )
        type_menu.pack(pady=2)
        # Name
        tb.Label(popup, text="Name:").pack()
        name_var = tk.StringVar(value=sensor["name"] if sensor else "")
        name_entry = tb.Entry(popup, textvariable=name_var)
        name_entry.pack(pady=2)
        # Port
        tb.Label(popup, text="Port:").pack()
        port_var = tk.StringVar(value=getattr(sensor, "port", ""))
        port_menu = tb.Combobox(
            popup,
            textvariable=port_var,
            values=[p.device for p in serial.tools.list_ports.comports()],
            state="readonly",
        )
        port_menu.pack(pady=2)

        def save():
            # Save or update sensor config
            if sensor:
                sensor["type"] = type_var.get()
                sensor["name"] = name_var.get()
                sensor["port"] = port_var.get()
            else:
                self.active_sensors.append(
                    {
                        "type": type_var.get(),
                        "name": name_var.get(),
                        "port": port_var.get(),
                        "icon": next(
                            (
                                t["icon"]
                                for t in self.sensor_templates
                                if t["type"] == type_var.get()
                            ),
                            "?",
                        ),
                        "fields": next(
                            (
                                t["fields"]
                                for t in self.sensor_templates
                                if t["type"] == type_var.get()
                            ),
                            [],
                        ),
                        "graph": next(
                            (
                                t["graph"]
                                for t in self.sensor_templates
                                if t["type"] == type_var.get()
                            ),
                            "line",
                        ),
                    }
                )
            self.build_sensors_tab()
            popup.destroy()

        tb.Button(popup, text="Save", command=save, bootstyle="success").pack(pady=10)

    def init_ai(self):
        """Initialize AI provider: OpenAI online or GPT4All offline, with graceful fallback."""
        self.ai_mode = "Disabled"
        self.ai_func = lambda q: "AI is disabled. Configure in Settings."
        provider = self.settings.get("ai_provider", "simple").lower()
        key = self.settings.get("openai_api_key", "").strip()
        # Try OpenAI if allowed
        tried_openai = False
        if provider in ("auto", "openai") and key:
            try:
                import openai  # type: ignore

                openai.api_key = key

                def _ask_openai(prompt: str) -> str:
                    try:
                        resp = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.2,
                            max_tokens=400,
                        )
                        return resp.choices[0].message["content"].strip()
                    except Exception as e:
                        return f"OpenAI error: {e}"

                self.ai_func = _ask_openai
                self.ai_mode = "Online (OpenAI)"
                tried_openai = True
                if hasattr(self, "ai_status_lbl"):
                    self.ai_status_lbl.config(text="AI: Online", bootstyle="success")
            except Exception:
                tried_openai = True
        # Try GPT4All if allowed or OpenAI failed
        if (
            self.ai_mode == "Disabled"
            and provider in ("auto", "gpt4all")
            and GPT4ALL_AVAILABLE
        ):
            try:
                from gpt4all import GPT4All  # type: ignore
                import time
                import os

                # Try to initialize GPT4All with better error handling
                # Use a more reliable model that's known to work
                model_name = "orca-mini-3b-gguf2-q4_0.gguf"

                # Check if model file exists and is not locked
                model_path = os.path.expanduser("~/.cache/gpt4all")
                model_file = os.path.join(model_path, model_name)

                if os.path.exists(model_file + ".part"):
                    # Model is still downloading, wait a bit
                    print("[AI] Model still downloading, waiting...")
                    time.sleep(2)

                print(f"[AI] Attempting to load GPT4All model: {model_name}")
                self.llm = GPT4All(model_name, allow_download=True, verbose=True)

                def _ask_gpt4all(prompt: str) -> str:
                    try:
                        if self.llm is None:
                            return "GPT4All model not loaded. Please restart the application."

                        # Simplified GPT4All generation for faster responses
                        try:
                            print(f"[AI] Generating response for: '{prompt[:50]}...'")
                            # Use simpler parameters for faster generation
                            response = self.llm.generate(
                                prompt, max_tokens=50, temp=0.1
                            ).strip()

                            print(f"[AI] GPT4All response: '{response[:100]}...'")

                            # Clean up the response
                            if response.startswith("User question:"):
                                response = response.split("User question:")[-1].strip()

                            # Return the response if we got one
                            if response and len(response) > 5:
                                print("[AI] Using GPT4All response")
                                return response
                            else:
                                # Fallback to simple AI if response is too short
                                print("[AI] GPT4All response too short, using fallback")
                                return self._simple_ai_fallback(prompt)

                        except Exception as e:
                            print(f"[AI] GPT4All generation error: {e}")
                            return self._simple_ai_fallback(prompt)
                    except Exception as e:
                        return f"GPT4All error: {e}"

                self.ai_func = _ask_gpt4all
                self.ai_mode = "Ready (GPT4All)"
                if hasattr(self, "ai_status_lbl"):
                    self.ai_status_lbl.config(text="AI: Ready", bootstyle="success")
                print(
                    "[AI] GPT4All initialized successfully (CPU mode - CUDA warnings are normal)"
                )
            except Exception as e:
                print(f"[AI] GPT4All initialization failed: {e}")
                # Try a different model as fallback
                try:
                    print("[AI] Trying fallback model: gpt4all-falcon-q4_0.gguf")
                    self.llm = GPT4All(
                        "gpt4all-falcon-q4_0.gguf", allow_download=True, verbose=True
                    )

                    def _ask_gpt4all_fallback(prompt: str) -> str:
                        try:
                            if self.llm is None:
                                return "GPT4All model not loaded. Please restart the application."
                            response = self.llm.generate(
                                prompt, max_tokens=200, temp=0.7
                            ).strip()
                            if response.startswith("User question:"):
                                response = response.split("User question:")[-1].strip()
                            return (
                                response
                                if response
                                else "I'm having trouble processing that request. Please try rephrasing your question."
                            )
                        except Exception as e:
                            return f"GPT4All error: {e}"

                    self.ai_func = _ask_gpt4all_fallback
                    self.ai_mode = "Ready (GPT4All-Falcon)"
                    if hasattr(self, "ai_status_lbl"):
                        self.ai_status_lbl.config(text="AI: Ready", bootstyle="success")
                    print("[AI] GPT4All Falcon model initialized successfully")
                except Exception as e2:
                    print(f"[AI] Fallback model also failed: {e2}")
                    # Set up a delayed retry
                    self.after(5000, self._retry_gpt4all_init)
                    pass
        # Use simple AI as default for fast responses
        if self.ai_mode == "Disabled" and provider in ("simple", "auto", "gpt4all"):
            if not tried_openai and not GPT4ALL_AVAILABLE:
                self.ai_func = (
                    lambda q: "No AI providers available. Install openai/gpt4all or set AI to None."
                )
            else:
                # Enhanced conversational AI for fast, natural responses
                def _simple_ai(prompt: str) -> str:
                    prompt_lower = prompt.lower()

                    # Greeting responses
                    if any(
                        word in prompt_lower
                        for word in ["hello", "hi", "hey", "greetings"]
                    ):
                        return "Hello! I'm your IoT assistant. I can help you with sensor data analysis, Arduino projects, and technical questions. What would you like to know?"

                    # General conversation
                    elif any(
                        word in prompt_lower
                        for word in ["how are you", "how's it going", "what's up"]
                    ):
                        return "I'm doing great! I'm here to help you with your IoT project. I can see you have sensors connected and data flowing in. What would you like to explore?"

                    # Weather/General questions
                    elif any(
                        word in prompt_lower
                        for word in ["weather", "temperature outside", "hot", "cold"]
                    ):
                        return "I can see your sensor data, but I don't have access to external weather data. However, I can help you interpret your temperature sensor readings! Your sensors show real-time environmental data."

                    # Chemical/Educational questions
                    elif "chemical formula" in prompt_lower and "water" in prompt_lower:
                        return "The chemical formula for water is H₂O - two hydrogen atoms and one oxygen atom. This is a fundamental compound in chemistry and essential for life!"

                    # Technology questions
                    elif any(
                        word in prompt_lower
                        for word in ["computer", "laptop", "technology", "programming"]
                    ):
                        return "I can help with programming and technology questions! For your IoT project, I can assist with Arduino code, sensor integration, and data analysis. What specific tech topic interests you?"

                    # Temperature questions
                    elif "temperature" in prompt_lower or "temp" in prompt_lower:
                        return "Temperature sensors like DHT11/DHT22 measure ambient temperature. Normal range is 0-50°C for most applications. Your current readings show real-time temperature data from your connected sensors."

                    # Humidity questions
                    elif "humidity" in prompt_lower or "hum" in prompt_lower:
                        return "Humidity sensors measure water vapor in air. Normal indoor range is 30-70% RH. Your sensor data shows current humidity levels that you can monitor in real-time."

                    # IMU/Motion questions
                    elif any(
                        word in prompt_lower
                        for word in [
                            "imu",
                            "gyro",
                            "accelerometer",
                            "motion",
                            "orientation",
                            "mpu6050",
                        ]
                    ):
                        return "IMU sensors (MPU6050) measure orientation and motion. Values are in degrees for pitch/roll/yaw. You can see the 3D orientation visualization in the Sensors tab when your MPU6050 is connected."

                    # Water quality questions
                    elif any(
                        word in prompt_lower
                        for word in ["tds", "water", "quality", "ppm"]
                    ):
                        return "TDS sensors measure water quality in parts per million (ppm). Lower values indicate purer water. Your TDS readings are displayed in real-time on the dashboard."

                    # Light/Color questions
                    elif any(
                        word in prompt_lower
                        for word in [
                            "spectrometer",
                            "as7341",
                            "light",
                            "color",
                            "spectrum",
                        ]
                    ):
                        return "AS7341 spectrometer measures light across different wavelengths. It's useful for color analysis and light sensing. The bar chart in the Sensors tab shows the spectral data from your AS7341 sensor."

                    # Help questions
                    elif any(
                        word in prompt_lower
                        for word in ["help", "what", "how", "explain"]
                    ):
                        return "I can help you with:\n• Sensor data interpretation\n• Arduino project guidance\n• IoT system troubleshooting\n• Data analysis and insights\n• General technical questions\n\nWhat specific question do you have?"

                    # Default response - more conversational and helpful
                    else:
                        return f"I understand you're asking about: '{prompt}'. I can help with sensor data analysis, Arduino projects, IoT systems, and general technical questions. Could you be more specific about what you'd like to know? For example, you could ask about your temperature readings, IMU orientation data, water quality measurements, or any other technical topic!"

                self.ai_func = _simple_ai
                self.ai_mode = "Simple Rules"
                if hasattr(self, "ai_status_lbl"):
                    self.ai_status_lbl.config(text="AI: Simple", bootstyle="warning")
        # Update AI status label
        if hasattr(self, "ai_status_lbl"):
            if self.ai_mode == "Disabled":
                self.ai_status_lbl.config(text="AI: Disabled", bootstyle="secondary")
            elif "GPT4All" in self.ai_mode:
                self.ai_status_lbl.config(text="AI: Ready", bootstyle="success")
            elif "OpenAI" in self.ai_mode:
                self.ai_status_lbl.config(text="AI: Online", bootstyle="success")
            elif "Simple" in self.ai_mode:
                self.ai_status_lbl.config(text="AI: Simple", bootstyle="warning")

    def _simple_ai_fallback(self, prompt: str) -> str:
        """Simple AI fallback for when GPT4All times out."""
        prompt_lower = prompt.lower()

        if any(word in prompt_lower for word in ["hello", "hi", "hey", "greetings"]):
            return "Hello! I'm your IoT assistant. I can help you with sensor data analysis, Arduino projects, and technical questions. What would you like to know?"
        elif "temperature" in prompt_lower or "temp" in prompt_lower:
            return "Temperature sensors like DHT11/DHT22 measure ambient temperature. Normal range is 0-50°C for most applications. Your current readings show real-time temperature data from your connected sensors."
        elif "humidity" in prompt_lower or "hum" in prompt_lower:
            return "Humidity sensors measure water vapor in air. Normal indoor range is 30-70% RH. Your sensor data shows current humidity levels that you can monitor in real-time."
        elif any(
            word in prompt_lower
            for word in [
                "imu",
                "gyro",
                "accelerometer",
                "motion",
                "orientation",
                "mpu6050",
            ]
        ):
            return "IMU sensors (MPU6050) measure orientation and motion. Values are in degrees for pitch/roll/yaw. You can see the 3D orientation visualization in the Sensors tab when your MPU6050 is connected."
        elif any(word in prompt_lower for word in ["tds", "water", "quality", "ppm"]):
            return "TDS sensors measure water quality in parts per million (ppm). Lower values indicate purer water. Your TDS readings are displayed in real-time on the dashboard."
        elif any(
            word in prompt_lower
            for word in ["spectrometer", "as7341", "light", "color", "spectrum"]
        ):
            return "AS7341 spectrometer measures light across different wavelengths. It's useful for color analysis and light sensing. The bar chart in the Sensors tab shows the spectral data from your AS7341 sensor."
        else:
            return f"I understand you're asking about: '{prompt}'. I can help with sensor data analysis, Arduino projects, and IoT systems. Could you be more specific about what you'd like to know?"

    def _retry_gpt4all_init(self):
        """Retry GPT4All initialization after a delay."""
        if self.ai_mode == "Disabled" and GPT4ALL_AVAILABLE:
            print("[AI] Retrying GPT4All initialization...")
            self.init_ai()

    def _ingest_template_sensor(self, sensor, data):
        s_type = sensor.get("type", "").upper()
        s_name = sensor.get("name", s_type)
        now = time.time() - self.start_time
        # Normalize floats
        for k, v in list(data.items()):
            try:
                data[k] = float(v)
            except Exception:
                pass
        if s_type in ("DHT11", "DHT22"):
            temp = float(data.get("TEMP", 0.0))
            hum = float(data.get("HUM", 0.0))
            self.append_dht_data(temp, hum)
            self.log_data("DHT", (temp, hum))
        elif s_type in ("MPU6050", "ITG/MPU6050"):
            self.yaw = float(data.get("YAW", 0.0))
            self.pitch = float(data.get("PITCH", 0.0))
            self.roll = float(data.get("ROLL", 0.0))
            self.log_data("3D Orientation", (self.yaw, self.pitch, self.roll))
            # Update meters if present
            w = self.imu_widgets.get(s_name)
            if w:
                try:
                    w.get("yaw").configure(amountused=self.yaw)
                    w.get("pitch").configure(amountused=self.pitch)
                    w.get("roll").configure(amountused=self.roll)
                except Exception:
                    pass
            self.update_3d_orientation()
            self.update_all_meters()
        elif s_type == "AS7341":
            # Spectrometer: baseline subtraction, normalize, smooth, update bars
            keys = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "CLEAR", "NIR"]
            state = self.as7341_state.setdefault(
                s_name, {"baseline": {}, "smoothed": [0.0] * 10}
            )
            baseline = state.get("baseline", {})
            vals = [
                max((data.get(k, 0.0) - baseline.get(k, 0.0)), 0.0) for k in keys[:8]
            ]
            max_val = max(vals) if max(vals) > 0 else 1.0
            normalized = [v / max_val for v in vals]
            alpha = 0.2
            smoothed = [
                alpha * n + (1 - alpha) * s
                for n, s in zip(normalized, state.get("smoothed", [0.0] * 8))
            ]
            state["smoothed"] = smoothed
            # If bars exist, update in-place
            bars = state.get("bars", [])
            if bars:
                try:
                    import matplotlib
                    from matplotlib.colors import LinearSegmentedColormap

                    bar_colors = [
                        [(148 / 255, 0, 211 / 255), (75 / 255, 0, 130 / 255)],
                        [(75 / 255, 0, 130 / 255), (0, 0, 1)],
                        [(0, 0, 1), (0, 1, 1)],
                        [(0, 1, 1), (0, 1, 0)],
                        [(0, 1, 0), (1, 1, 0)],
                        [(1, 1, 0), (1, 127 / 255, 0)],
                        [(1, 127 / 255, 0), (1, 0, 0)],
                        [(1, 0, 0), (148 / 255, 0, 211 / 255)],
                    ]
                    for i, bar in enumerate(bars):
                        cmap = LinearSegmentedColormap.from_list(
                            f"bar{i}", bar_colors[i]
                        )
                        bar.set_height(smoothed[i])
                        bar.set_color(cmap(smoothed[i]))
                    canvas = state.get("canvas")
                    if canvas:
                        canvas.draw()
                except Exception:
                    pass
            else:
                # No bars yet; request UI to build the card (debounced)
                self.request_sensors_refresh()
            self.log_data("AS7341", tuple(vals))
        else:
            # Generic multi-field ingest into generic_streams
            stream = self.generic_streams.setdefault(s_name, {"time": []})
            stream["time"].append(now)
            for f in sensor.get("fields", []):
                stream.setdefault(f, []).append(float(data.get(f, 0.0)))
                # limit
                stream[f] = stream[f][-200:]
            stream["time"] = stream["time"][-200:]
            self.log_data(
                s_type, tuple(data.get(f, None) for f in sensor.get("fields", []))
            )
            self.request_sensors_refresh()

    def _parse_csv_sensor_line(self, line: str) -> bool:
        # Handle lines like: SENSOR,VAL[,VAL2,VAL3]
        try:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                return False
            sensor_type = parts[0].upper()
            # Find matching active sensor by type or alias
            match_sensor = None
            for s in self.active_sensors:
                t = s.get("type", "").upper()
                if t == sensor_type:
                    match_sensor = s
                    break
                if sensor_type == "MPU6050" and t in ("MPU6050", "ITG/MPU6050"):
                    match_sensor = s
                    break
            # If not found, auto-attach a sensor from templates
            if match_sensor is None:
                tpl = self._get_template_by_type(sensor_type)
                if tpl is None:
                    fields = [f"F{i + 1}" for i in range(len(parts) - 1)]
                    match_sensor = {
                        "type": sensor_type,
                        "name": sensor_type,
                        "port": "",
                        "icon": "🧩",
                        "fields": fields,
                        "graph": "single-line" if len(fields) == 1 else "dual-line",
                        "_compiled": None,
                        "_labels": {f: f for f in fields},
                        "_ranges": {},
                    }
                else:
                    match_sensor = {
                        "type": sensor_type,
                        "name": sensor_type,
                        "port": "",
                        "icon": tpl.get("icon", "🧩"),
                        "fields": tpl.get("fields", []),
                        "graph": tpl.get("graph_type", "single-line"),
                        "_compiled": tpl.get("_compiled"),
                        "_labels": tpl.get("labels", {}),
                        "_ranges": tpl.get("ranges", {}),
                    }
                self.active_sensors.append(match_sensor)
                if match_sensor["name"] not in self.generic_streams:
                    self.generic_streams[match_sensor["name"]] = {"time": []}
                    for f in match_sensor.get("fields", []):
                        self.generic_streams[match_sensor["name"]][f] = []
                try:
                    self.build_sensors_tab()
                except Exception:
                    pass
            # Map values to fields in order
            values = []
            for v in parts[1:]:
                try:
                    values.append(float(v))
                except Exception:
                    values.append(0.0)
            fields = match_sensor.get("fields", [])
            # Special case: DS18B20 sometimes outputs -127 as error; ignore
            if sensor_type == "DS18B20" and len(values) >= 1 and values[0] <= -120:
                return True
            # Special case: MPU6050 CSV with only 2 values -> assume Pitch, Roll
            if (
                sensor_type in ("MPU6050", "ITG/MPU6050")
                and len(fields) == 3
                and len(values) == 2
            ):
                values = [0.0] + values
            # Pad or trim to fields length
            if len(values) < len(fields):
                values += [0.0] * (len(fields) - len(values))
            if len(values) > len(fields):
                values = values[: len(fields)]
            data = {f: values[i] for i, f in enumerate(fields)}
            try:
                self.after(
                    0, lambda s=match_sensor, d=data: self._ingest_template_sensor(s, d)
                )
            except Exception as e:
                print(f"[CSV PARSE WARN] {e}")
            return True
        except Exception:
            return False

    def _try_parse_as7341(self, line: str) -> bool:
        # Supports lines like:
        #  "AS7341, F1:123, F2:456, ..., CLEAR:789, NIR:101"
        #  or per-line prints like "F1 415nm: 123"
        keys = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "CLEAR", "NIR"]
        rx = re.compile(
            r"\b(F[1-8]|CLEAR|NIR)\b(?:\s*\d*nm)?\s*:\s*(-?\d+(?:\.\d+)?)",
            re.IGNORECASE,
        )
        matches = rx.findall(line)
        if not matches and not line.upper().startswith("AS7341"):
            return False
        # If it is an AS7341 line with CSV of only numbers, let CSV parser handle it
        if line.upper().startswith("AS7341,") and ":" not in line:
            return False
        now = time.time()
        # Reset buffer if stale
        if now - self._as7341_buf.get("t", 0) > 1.5:
            self._as7341_buf = {"data": {}, "t": now}
        self._as7341_buf["t"] = now
        # Accumulate any key:value pairs in the line
        for k, v in matches:
            try:
                self._as7341_buf["data"][k.upper()] = float(v)
            except Exception:
                pass
        # If we have all keys, ingest
        if all(k in self._as7341_buf["data"] for k in keys):
            data = {k: self._as7341_buf["data"][k] for k in keys}
            # Find or add sensor
            sensor = None
            for s in self.active_sensors:
                if s.get("type", "").upper() == "AS7341":
                    sensor = s
                    break
            if sensor is None:
                tpl = self._get_template_by_type("AS7341") or {}
                sensor = {
                    "type": "AS7341",
                    "name": "AS7341",
                    "port": "",
                    "icon": tpl.get("icon", "🌈"),
                    "fields": tpl.get("fields", keys),
                    "graph": tpl.get("graph_type", "multi-line"),
                    "_compiled": tpl.get("_compiled"),
                    "_labels": tpl.get("labels", {k: k for k in keys}),
                    "_ranges": tpl.get("ranges", {}),
                }
                self.active_sensors.append(sensor)
                if sensor["name"] not in self.generic_streams:
                    self.generic_streams[sensor["name"]] = {"time": []}
                    for f in sensor.get("fields", []):
                        self.generic_streams[sensor["name"]][f] = []
                self.request_sensors_refresh()
            # Ingest through the same path as generic sensors
            self._ingest_template_sensor(sensor, data)
            # Reset buffer for next frame
            self._as7341_buf = {"data": {}, "t": now}
            return True
        return bool(matches)


if __name__ == "__main__":
    app = SeaLinkApp()
    app.mainloop()
