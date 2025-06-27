import tkinter as tk
from tkinter import messagebox
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


class SeaLinkApp(tb.Window):
    def __init__(self):
        super().__init__(themename="superhero")
        self.title("SeaLink Dashboard")
        self.geometry("1200x750")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

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

        self.build_gui()
        self.refresh_ports()
        self.schedule_simulation()

    def build_gui(self):
        # Navbar
        navbar = tb.Frame(self)
        navbar.pack(fill=X, pady=5)

        tb.Label(navbar, text="SeaLink", font=("Segoe UI", 20, "bold"), bootstyle="info").pack(side=LEFT, padx=10)

        self.port_var = tk.StringVar()
        self.port_menu = tb.Combobox(navbar, textvariable=self.port_var, width=20, bootstyle="info")
        self.port_menu.pack(side=LEFT, padx=5)

        tb.Button(navbar, text="Refresh", command=self.refresh_ports, bootstyle="secondary").pack(side=LEFT, padx=5)
        self.connect_btn = tb.Button(navbar, text="Connect", command=self.connect_serial, bootstyle="success")
        self.connect_btn.pack(side=LEFT, padx=5)
        self.disconnect_btn = tb.Button(navbar, text="Disconnect", command=self.disconnect_serial,
                                        bootstyle="danger", state=DISABLED)
        self.disconnect_btn.pack(side=LEFT, padx=5)

        self.calib_btn = tb.Button(navbar, text="Calibrate", command=self.calibrate_sensor, bootstyle="warning",
                                   state=DISABLED)
        self.calib_btn.pack(side=LEFT, padx=5)

        self.status_lbl = tb.Label(navbar, text="Disconnected", bootstyle="warning")
        self.status_lbl.pack(side=RIGHT, padx=20)

        # Tabs
        self.tabs = tb.Notebook(self)
        self.tabs.pack(expand=True, fill=BOTH, padx=10, pady=10)

        self.tab_3d = tb.Frame(self.tabs)
        self.tab_dht = tb.Frame(self.tabs)
        self.tabs.add(self.tab_3d, text="3D Orientation")
        self.tabs.add(self.tab_dht, text="DHT Sensor")

        self.build_3d_plot()
        self.build_dht_plot()

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_menu['values'] = ports
        if ports:
            self.port_var.set(ports[0])

    def connect_serial(self):
        port = self.port_var.get()
        try:
            self.serial_conn = serial.Serial(port, 9600, timeout=1)
            time.sleep(2)
            self.is_connected = True
            self.status_lbl.config(text=f"Connected: {port}", bootstyle="success")
            self.connect_btn.config(state=DISABLED)
            self.disconnect_btn.config(state=NORMAL)
            self.calib_btn.config(state=NORMAL)
            self.send_flash()

            self.read_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.read_thread.start()
        except Exception as e:
            messagebox.showerror("Connection Failed", str(e))

    def disconnect_serial(self):
        self.is_connected = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.status_lbl.config(text="Disconnected", bootstyle="warning")
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
        self.calib_btn.config(state=DISABLED)

    def send_flash(self):
        try:
            for _ in range(2):
                self.serial_conn.write(b'F')
                time.sleep(0.2)
        except:
            pass

    def calibrate_sensor(self):
        self.cal_yaw = self.yaw
        self.cal_pitch = self.pitch
        self.cal_roll = self.roll

    def read_serial(self):
        while self.is_connected:
            try:
                line = self.serial_conn.readline().decode('utf-8').strip()
                if line.startswith("YAW"):
                    parts = line.split()
                    self.yaw = float(parts[0].split(":")[1])
                    self.pitch = float(parts[1].split(":")[1])
                    self.roll = float(parts[2].split(":")[1])
                    temp = float(parts[3].split(":")[1])
                    hum = float(parts[4].split(":")[1])
                    self.append_dht_data(temp, hum)
                    self.update_3d_orientation()
            except:
                continue

    def build_dht_plot(self):
        self.fig = Figure(figsize=(6, 5), dpi=100)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.tab_dht)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=True)

    def append_dht_data(self, temp, hum):
        t = time.time() - self.start_time
        self.time_data.append(t)
        self.temp_data.append(temp)
        self.hum_data.append(hum)
        self.trim_data()
        self.update_dht_plot()

    def update_dht_plot(self):
        self.ax1.clear()
        self.ax2.clear()

        self.ax1.plot(self.time_data, self.temp_data, color='red')
        self.ax1.set_ylabel("Temp (°C)")
        self.ax1.set_title("Temperature")

        self.ax2.plot(self.time_data, self.hum_data, color='blue')
        self.ax2.set_ylabel("Humidity (%)")
        self.ax2.set_xlabel("Time (s)")
        self.ax2.set_title("Humidity")

        self.ax1.grid(True)
        self.ax2.grid(True)
        self.canvas.draw()

    def trim_data(self, max_len=100):
        self.time_data = self.time_data[-max_len:]
        self.temp_data = self.temp_data[-max_len:]
        self.hum_data = self.hum_data[-max_len:]

    def build_3d_plot(self):
        fig3d = Figure(figsize=(6, 5), dpi=100)
        self.ax3d = fig3d.add_subplot(111, projection='3d')
        self.ax3d.set_xlim([-1, 1])
        self.ax3d.set_ylim([-1, 1])
        self.ax3d.set_zlim([-1, 1])
        self.ax3d.set_title("3D Orientation")

        self.cube_data = self.make_cube()
        self.plot_cube(*self.cube_data)

        self.canvas3d = FigureCanvasTkAgg(fig3d, master=self.tab_3d)
        self.canvas3d.draw()
        self.canvas3d.get_tk_widget().pack(fill=BOTH, expand=True)

    def make_cube(self, size=0.5):
        r = [-size, size]
        x, y, z = np.meshgrid(r, r, r)
        return np.array([x.flatten(), y.flatten(), z.flatten()])

    def plot_cube(self, x, y, z):
        self.ax3d.cla()
        self.ax3d.set_xlim([-1, 1])
        self.ax3d.set_ylim([-1, 1])
        self.ax3d.set_zlim([-1, 1])
        self.ax3d.set_title("3D Orientation")
        self.ax3d.scatter(x, y, z, color='skyblue')
        for i in range(8):
            for j in range(i+1, 8):
                if np.sum(np.abs(np.array([x[i], y[i], z[i]]) - np.array([x[j], y[j], z[j]]))) == 1.0:
                    self.ax3d.plot([x[i], x[j]], [y[i], y[j]], [z[i], z[j]], color='blue')

    def update_3d_orientation(self):
        yaw = radians(self.yaw - self.cal_yaw)
        pitch = radians(self.pitch - self.cal_pitch)
        roll = radians(self.roll - self.cal_roll)

        Rz = np.array([
            [cos(yaw), -sin(yaw), 0],
            [sin(yaw), cos(yaw), 0],
            [0, 0, 1]
        ])
        Ry = np.array([
            [cos(pitch), 0, sin(pitch)],
            [0, 1, 0],
            [-sin(pitch), 0, cos(pitch)]
        ])
        Rx = np.array([
            [1, 0, 0],
            [0, cos(roll), -sin(roll)],
            [0, sin(roll), cos(roll)]
        ])

        rotated = Rz @ Ry @ Rx @ self.cube_data
        self.plot_cube(rotated[0], rotated[1], rotated[2])
        self.canvas3d.draw()

    def schedule_simulation(self):
        if not self.is_connected:
            t = time.time() - self.start_time
            self.time_data.append(t)
            self.temp_data.append(24 + np.sin(t / 5) * 2)
            self.hum_data.append(60 + np.cos(t / 4) * 5)
            self.trim_data()
            self.update_dht_plot()
        self.after_job = self.after(1000, self.schedule_simulation)

    def on_close(self):
        self.is_connected = False
        if self.after_job:
            self.after_cancel(self.after_job)
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.destroy()


if __name__ == "__main__":
    app = SeaLinkApp()
    app.mainloop()
