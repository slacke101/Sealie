import sys
import json
from PIL import Image, ImageTk

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
        self.title("SeaLink Dashboard")
        self.geometry("1200x800")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.resizable(True, True)
        # Modern, professional color palette (black, teal, silver)
        self.night_mode = True
        self.colors = {
            "night": {
                "bg": "#101214",  # deep black
                "sidebar": "#181A1B",  # almost black
                "topbar": "#181A1B",  # almost black
                "card": "#23272A",  # graphite dark
                "fg": "#F5F6FA",  # off-white
                "accent": "#20CFCF",  # teal
                "highlight": "#C0C0C0",  # silver
                "shadow": "#0A0B0C",  # shadow for depth
            },
            "day": {
                "bg": "#F5F6FA",  # off-white
                "sidebar": "#E0E0E0",  # silver
                "topbar": "#C0C0C0",  # silver
                "card": "#FFFFFF",  # white
                "fg": "#181A1B",  # almost black
                "accent": "#20CFCF",  # teal
                "highlight": "#23272A",  # graphite
                "shadow": "#B0B0B0",  # shadow for depth
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

        # Sensor data
        self.time_data, self.temp_data, self.hum_data = [], [], []
        self.yaw, self.pitch, self.roll = 0, 0, 0
        self.cal_yaw, self.cal_pitch, self.cal_roll = 0, 0, 0
        self.start_time = time.time()

        self.sensor_templates = [
            {
                "type": "DHT",
                "name": "DHT Sensor",
                "icon": "🌡️",
                "fields": ["Temperature (°C)", "Humidity (%)"],
                "graph": "line",
            },
            {
                "type": "IMU",
                "name": "3D Orientation",
                "icon": "🧭",
                "fields": ["Yaw (°)", "Pitch (°)", "Roll (°)"],
                "graph": "line3d",
            },
            # Add more templates here (ECG, Pulse, Gas, etc.)
        ]
        self.active_sensors = []  # List of dicts: {type, name, port, ...}

        self.data_log = []  # List of dicts: {timestamp, sensor, values}
        self.is_recording = False
        self.recording_file = None

        if GPT4ALL_AVAILABLE:
            # NOTE: You must download a compatible model, e.g. 'gpt4all-falcon-q4_0.gguf', and place it in the default gpt4all models directory.
            self.llm = GPT4All("gpt4all-falcon-q4_0.gguf", allow_download=False)
        else:
            self.llm = None

        self.build_layout()
        self.refresh_ports()
        self.schedule_simulation()
        self.apply_theme()

    def load_settings(self):
        """Load settings from settings.json file."""
        try:
            with open(self.settings_file, "r") as f:
                settings = json.load(f)
                # Set default values if not present
                if "baud_rate" not in settings:
                    settings["baud_rate"] = 9600
                if "theme" not in settings:
                    settings["theme"] = "superhero"
                return settings
        except:
            # Return default settings if file doesn't exist or is invalid
            return {"baud_rate": 9600, "theme": "superhero"}

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

            self.is_recording = True
            self.record_btn.config(text="Stop Recording", bootstyle="danger-outline")
            self.recording_file = open(
                f"sealink_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "w",
                newline="",
            )
            import csv

            self.csv_writer = csv.writer(self.recording_file)
            self.csv_writer.writerow(
                ["Timestamp", "Sensor", "Value1", "Value2", "Value3"]
            )
            self.show_notification("Recording started", style="success")
        else:
            self.is_recording = False
            self.record_btn.config(text="Start Recording", bootstyle="primary-outline")
            if self.recording_file:
                self.recording_file.close()
                self.recording_file = None
            self.show_notification("Recording stopped", style="warning")

    def log_data(self, sensor, values):
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {"timestamp": timestamp, "sensor": sensor, "values": values}
        self.data_log.append(entry)
        if self.is_recording and self.recording_file:
            self.csv_writer.writerow([timestamp, sensor] + list(values)[:3])

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
        # Hamburger icon in topbar
        self.hamburger_icon = tb.Button(
            self.topbar,
            text="☰",
            cursor="hand2",
            bootstyle="info-outline",
            width=3,
        )
        self.hamburger_icon.pack(side=LEFT, padx=10)
        self.hamburger_icon.bind("<Button-1>", self.toggle_sidebar)
        self.hamburger_icon.bind("<B1-Motion>", self.drag_sidebar)

        # Sidebar overlay (hidden by default)
        self.sidebar_expanded = False
        self.sidebar_width = 0
        self.sidebar_min_width = 48
        self.sidebar_max_width = 220
        self.sidebar = tb.Frame(
            self.container, width=self.sidebar_min_width, bootstyle="dark"
        )
        self.sidebar.place(x=0, y=0, relheight=1)
        self.sidebar.pack_propagate(False)

        # Sidebar content (hidden by default)
        self.sidebar_content = tb.Frame(self.sidebar, bootstyle="dark")
        self.sidebar_content.pack(pady=(10, 0), fill=Y, expand=True)
        self.sidebar_content.pack_forget()

        # Close button for sidebar (hidden by default)
        self.close_sidebar_btn = tb.Button(
            self.sidebar_content,
            text="✕",
            cursor="hand2",
            bootstyle="danger-outline",
            width=3,
            command=self.toggle_sidebar,
        )
        self.close_sidebar_btn.pack(anchor="ne", padx=10, pady=5)  # Top-right corner
        self.close_sidebar_btn.pack_forget()  # Hide initially

        # Logo and app name
        logo_frame = tb.Frame(self.sidebar_content, bootstyle="dark")
        logo_frame.pack(pady=(10, 10))
        logo_img = Image.open("Sealielogo.png")
        logo_img = logo_img.resize((48, 48), Image.LANCZOS)
        self.logo_photo = ImageTk.PhotoImage(logo_img)
        logo_label = tk.Label(logo_frame, image=self.logo_photo)
        logo_label.pack()
        app_name = tb.Label(
            logo_frame,
            text="SeaLink",
            font=("Segoe UI", 18, "bold"),
        )
        app_name.pack()
        # Navigation buttons
        self.nav_dashboard = tb.Button(
            self.sidebar_content,
            text="Dashboard",
            command=lambda: self.show_tab(0),
            bootstyle="dark",
        )
        self.nav_dashboard.pack(fill=X, pady=(30, 10), padx=20)
        self.add_hover(self.nav_dashboard)
        self.create_tooltip(self.nav_dashboard, "Show dashboard overview")
        self.nav_sensors = tb.Button(
            self.sidebar_content,
            text="Sensors",
            command=lambda: self.show_tab(1),
            bootstyle="dark",
        )
        self.nav_sensors.pack(fill=X, pady=10, padx=20)
        self.add_hover(self.nav_sensors)
        self.create_tooltip(self.nav_sensors, "View and manage sensors")
        self.nav_data = tb.Button(
            self.sidebar_content,
            text="Data",
            command=lambda: self.show_tab(2),
            bootstyle="dark",
        )
        self.nav_data.pack(fill=X, pady=10, padx=20)
        self.add_hover(self.nav_data)
        self.create_tooltip(self.nav_data, "View and export sensor data")
        tb.Label(self.sidebar_content, text="").pack(expand=True, fill=Y)
        self.nav_settings = tb.Button(
            self.sidebar_content,
            text="Settings",
            command=self.show_settings,
            bootstyle="dark",
        )
        self.nav_settings.pack(fill=X, pady=5, padx=20)
        self.add_hover(self.nav_settings)
        self.create_tooltip(self.nav_settings, "Open settings dialog")
        self.nav_about = tb.Button(
            self.sidebar_content,
            text="About",
            command=lambda: self.show_tab(4),
            bootstyle="dark",
        )
        self.nav_about.pack(fill=X, pady=(0, 30), padx=20)
        self.add_hover(self.nav_about)
        self.create_tooltip(self.nav_about, "Show about info")

        # Status and quick actions (rest of topbar)
        self.status_lbl = tb.Label(
            self.topbar,
            text="Disconnected",
            bootstyle="warning",
            font=("Segoe UI", 11, "bold"),
        )
        self.status_lbl.pack(side=RIGHT, padx=20)
        self.theme_btn = tb.Button(
            self.topbar,
            text="Night/Day Mode",
            command=self.toggle_theme,
            bootstyle="info-outline",
        )
        self.theme_btn.pack(side=RIGHT, padx=10)
        self.add_hover(self.theme_btn)
        self.create_tooltip(self.theme_btn, "Switch between night and day mode")
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
        # Only set bg/fg for classic Tk widgets in sidebar
        for w in self.sidebar.winfo_children():
            if isinstance(w, tk.Frame) or isinstance(w, tk.Label):
                try:
                    w.configure(bg=c["sidebar"], fg=c["fg"])
                except:
                    pass
        # Use bootstyle for ttkbootstrap widgets
        self.sidebar.configure(bootstyle="dark" if self.night_mode else "warning")
        self.topbar.configure(bootstyle="dark" if self.night_mode else "warning")
        # self.content.configure(bg=c['bg'])  # Removed: tb.Frame does not support bg
        for tab in self.tabs:
            # tab.configure(bg=c['card'])  # Removed: tb.Frame does not support bg
            pass
        # Update plot backgrounds if needed
        if hasattr(self, "fig"):
            self.fig.patch.set_facecolor(c["card"])
            self.ax1.set_facecolor(c["card"])
            self.ax2.set_facecolor(c["card"])
            self.canvas.draw()
        if hasattr(self, "ax3d"):
            self.ax3d.set_facecolor(c["card"])
            self.canvas3d.draw()

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
                print(f"[SERIAL] {line}")  # Print every received line to the console

                # Try to parse known formats
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
        """Update all meters and graphs with current sensor data."""
        # Update dashboard meters if they exist
        if hasattr(self, "dashboard_meters"):
            for meter in self.dashboard_meters:
                try:
                    meter.destroy()
                except:
                    pass

        # Update sensor tab meters if they exist
        if hasattr(self, "sensor_meters"):
            for meter in self.sensor_meters:
                try:
                    meter.destroy()
                except:
                    pass

        # Rebuild dashboard and sensors tab to show updated data
        if hasattr(self, "tab_dashboard"):
            self.build_dashboard()
        if hasattr(self, "tab_sensors"):
            self.build_sensors_tab()

    def build_sensors_tab(self):
        for w in self.tab_sensors.winfo_children():
            w.destroy()
        tb.Label(self.tab_sensors, text="Sensors", font=("Segoe UI", 18, "bold")).pack(
            pady=20
        )
        sensors_frame = tb.Frame(self.tab_sensors)
        sensors_frame.pack(pady=10)
        # Show all active sensors
        for sensor in self.active_sensors:
            self.build_sensor_card(sensors_frame, sensor)
        # Add sensor section (button only, uses dialog)
        add_frame = tb.Frame(self.tab_sensors)
        add_frame.pack(pady=20)
        tb.Button(
            add_frame,
            text="Add Sensor",
            command=self.open_add_sensor_dialog,
            bootstyle="primary-outline",
        ).pack(side=LEFT, padx=5)

    def build_sensor_card(self, parent, sensor):
        card = tb.Frame(parent, bootstyle="secondary", borderwidth=2, relief="ridge")
        card.pack(pady=10, padx=10, fill=X)
        # Sensor header row
        header_row = tb.Frame(card)
        header_row.pack(fill=X, pady=(10, 0))
        tb.Label(
            header_row,
            text=f"{sensor['icon']} {sensor['name']}",
            font=("Segoe UI", 14, "bold"),
        ).pack(side=LEFT, padx=10)
        status = "Connected" if self.is_connected else "Not Connected"
        tb.Label(
            header_row,
            text=status,
            font=("Segoe UI", 12, "bold"),
            bootstyle="success" if self.is_connected else "danger",
        ).pack(side=LEFT, padx=10)
        tb.Button(
            header_row,
            text="Configure",
            command=lambda s=sensor: self.configure_sensor(s),
            bootstyle="info-outline",
        ).pack(side=RIGHT, padx=5)
        tb.Button(
            header_row,
            text="Remove",
            command=lambda: self.remove_sensor(sensor),
            bootstyle="danger-outline",
        ).pack(side=RIGHT, padx=5)
        # Live data/graph and meters
        if sensor["type"] == "DHT":
            # Add meters for temp/humidity
            temp_val = self.temp_data[-1] if self.temp_data else 0
            hum_val = self.hum_data[-1] if self.hum_data else 0
            meter_row = tb.Frame(card)
            meter_row.pack(pady=5)
            tb.Meter(
                meter_row,
                amountused=temp_val,
                metertype="full",
                subtext="Temp (°C)",
                bootstyle="info",
                stripethickness=6,
                interactive=False,
                amounttotal=50,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            ).pack(side=LEFT, padx=10)
            tb.Meter(
                meter_row,
                amountused=hum_val,
                metertype="full",
                subtext="Humidity (%)",
                bootstyle="success",
                stripethickness=6,
                interactive=False,
                amounttotal=100,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            ).pack(side=LEFT, padx=10)
            self.build_dht_plot(parent=card, compact=True, sensor_name=sensor["name"])
        elif sensor["type"] == "IMU":
            meter_row = tb.Frame(card)
            meter_row.pack(pady=5)
            tb.Meter(
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
            ).pack(side=LEFT, padx=10)
            tb.Meter(
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
            ).pack(side=LEFT, padx=10)
            tb.Meter(
                meter_row,
                amountused=self.roll,
                metertype="full",
                subtext="Roll (°)",
                bootstyle="danger",
                stripethickness=6,
                interactive=False,
                amounttotal=180,
                textfont=("Segoe UI", 10, "bold"),
                subtextfont=("Segoe UI", 9),
                metersize=90,
            ).pack(side=LEFT, padx=10)
            self.build_3d_plot(parent=card, compact=True)
        # Add more sensor types here

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
        else:
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
        except Exception as e:
            print(f"[ERROR] 3D orientation update failed: {e}")

    def schedule_simulation(self):
        # Only update plots if connected; do not simulate data
        if self.is_connected:
            self.update_dht_plot()
        self.after_job = self.after(1000, self.schedule_simulation)

    def open_add_sensor_dialog(self):
        # Dialog for adding a sensor
        popup = tk.Toplevel(self)
        popup.title("Add Sensor")
        popup.geometry("350x260")
        popup.title("AI Analysis Result")
        img = Image.open(img_path)
        img = img.resize((400, 300), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(popup, image=photo)
        label.image = photo
        label.pack()

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
        tb.Label(
            self.tab_about,
            text="About SeaLink Dashboard\nVersion 1.0\nA professional dashboard for sensor data visualization.",
            font=("Segoe UI", 14),
        ).pack(pady=30)

    def show_settings(self):
        """
        Show the Settings dialog for theme and serial options.
        """
        settings = tk.Toplevel(self)
        settings.title("Settings")
        settings.geometry("350x220")
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

        def save_settings():
            self.settings["theme"] = theme_var.get()
            self.settings["baud_rate"] = int(baud_var.get())
            self.save_settings()
            # Apply theme immediately
            self.style.theme_use(self.settings["theme"])
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
        header = tb.Frame(self.tab_dashboard)
        header.pack(fill=X, pady=(20, 10))
        logo_img = Image.open("Sealielogo.png")
        logo_img = logo_img.resize((48, 48), Image.LANCZOS)
        logo_photo = ImageTk.PhotoImage(logo_img)
        logo_label = tk.Label(header, image=logo_photo)
        logo_label.image = logo_photo
        logo_label.pack(side=LEFT, padx=10)
        tb.Label(
            header, text="Welcome to SeaLink Dashboard!", font=("Segoe UI", 22, "bold")
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
        # Show professional meters for DHT and IMU sensors
        for sensor in self.active_sensors:
            meter_card = tb.Frame(
                meters_frame,
                bootstyle="light",
                borderwidth=1,
                relief="solid",
                padx=16,
                pady=16,
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
        # Recent activity/log (placeholder)
        log_frame = tb.Frame(self.tab_dashboard)
        log_frame.pack(fill=BOTH, expand=True, pady=10)
        tb.Label(
            log_frame,
            text="Recent Activity",
            font=("Segoe UI", 12, "italic"),
            bootstyle="secondary",
        ).pack(anchor="w", padx=10)
        log_text = tk.Text(log_frame, height=6, state="normal")
        for line in getattr(self, "_serial_debug_log", [])[-10:]:
            log_text.insert(tk.END, line + "\n")
        log_text.config(state="disabled")
        log_text.pack(fill=BOTH, expand=True, padx=10, pady=5)

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
        tb.Label(self.tab_data, text="Data", font=("Segoe UI", 18, "bold")).pack(
            pady=20
        )
        # Table of logged data
        table_frame = tb.Frame(self.tab_data)
        table_frame.pack(pady=10, fill=BOTH, expand=True)
        columns = ("Timestamp", "Sensor", "Value1", "Value2", "Value3")
        self.data_table = tb.Treeview(
            table_frame, columns=columns, show="headings", height=15
        )
        for col in columns:
            self.data_table.heading(col, text=col)
            self.data_table.column(col, width=120)
        self.data_table.pack(fill=BOTH, expand=True)
        for entry in self.data_log:
            vals = list(entry["values"]) + ["", ""]
            self.data_table.insert(
                "",
                "end",
                values=(entry["timestamp"], entry["sensor"], vals[0], vals[1], vals[2]),
            )
        tb.Button(
            self.tab_data,
            text="Export All Data",
            command=self.export_all_data,
            bootstyle="info-outline",
        ).pack(pady=10)
        # Graph area (placeholder)
        graph_frame = tb.Frame(self.tab_data)
        graph_frame.pack(pady=10, fill=BOTH, expand=True)
        tb.Label(
            graph_frame,
            text="Graph View (Coming Soon)",
            font=("Segoe UI", 14, "italic"),
            bootstyle="secondary",
        ).pack(pady=20)
        # AI Data Assistant (offline)
        ai_frame = tb.Frame(self.tab_data)
        ai_frame.pack(pady=10, fill=BOTH, expand=True)
        tb.Label(
            ai_frame,
            text="AI Data Assistant",
            font=("Segoe UI", 12, "bold"),
            bootstyle="info",
        ).pack(anchor="w", padx=10)
        self.ai_chat_log = tk.Text(ai_frame, height=10, state="disabled", wrap="word")
        self.ai_chat_log.pack(fill=BOTH, expand=True, padx=10, pady=5)
        chat_entry_frame = tb.Frame(ai_frame)
        chat_entry_frame.pack(fill=X, padx=10, pady=5)
        self.ai_chat_entry = tb.Entry(chat_entry_frame)
        self.ai_chat_entry.pack(side=LEFT, fill=X, expand=True)
        tb.Button(
            chat_entry_frame,
            text="Send",
            command=self.handle_ai_chat,
            bootstyle="primary-outline",
        ).pack(side=LEFT, padx=5)

    def handle_ai_chat(self):
        user_msg = self.ai_chat_entry.get().strip()
        if not user_msg:
            return
        self.ai_chat_entry.delete(0, tk.END)
        self.append_ai_chat(f"You: {user_msg}\n")
        response = self.process_ai_query(user_msg)
        self.append_ai_chat(f"AI: {response}\n")

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

    def toggle_sidebar(self, event=None):
        if self.sidebar_expanded:
            self.sidebar_content.pack_forget()
            self.sidebar.configure(width=self.sidebar_min_width)
            self.sidebar_expanded = False
            self.close_sidebar_btn.pack_forget()  # Hide close button
        else:
            self.sidebar_content.pack(pady=(10, 0), fill=Y, expand=True)
            self.sidebar.configure(width=self.sidebar_max_width)
            self.sidebar.lift()
            self.sidebar_expanded = True
            self.close_sidebar_btn.pack(
                anchor="ne", padx=10, pady=5
            )  # Show close button

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


if __name__ == "__main__":
    app = SeaLinkApp()
    app.mainloop()
