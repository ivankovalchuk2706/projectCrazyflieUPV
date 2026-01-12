import logging
import csv
import datetime
from pathlib import Path

# --- PyQt6 Imports ---
from PyQt6.QtWidgets import (QVBoxLayout, QLabel, QGroupBox, QGridLayout, 
                             QFrame, QWidget, QPushButton, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont

# --- Graph Import ---
import pyqtgraph as pg

# --- CFClient UI Import ---
from cfclient.ui.tab_toolbox import TabToolbox

# --- CFLib Imports ---
import cflib.crtp
from cflib.crazyflie.log import LogConfig

class NiclaTab(TabToolbox):
    """
    Вкладка Nicla Sense ME з графіками та експортом даних
    """
    
    def __init__(self, tab_api):
        super(NiclaTab, self).__init__(tab_api, "Nicla Monitor")
        
        # --- Зберігання даних ---
        # data_storage: список для запису ВСІХ даних для збереження в файл
        # plot_buffers: списки для відображення на графіку (тільки останні N точок)
        self.data_storage = [] 
        self.buffer_size = 200 # Скільки точок показувати на екрані
        self.ptr = 0 # Лічильник пакетів
        
        self.buf_temp = [0.0] * self.buffer_size
        self.buf_hum = [0.0] * self.buffer_size
        self.buf_gas = [0.0] * self.buffer_size

        # --- GUI Setup ---
        layout = QVBoxLayout()
        
        # 1. Блок поточних значень (як було раніше)
        group_vals = QGroupBox("Current Values")
        group_vals.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        grid_vals = QGridLayout()
        
        title_font = QFont("Arial", 10)
        value_font = QFont("Arial", 18)
        value_font.setBold(True)
        
        # Temp
        self.lbl_temp = QLabel("--.- °C")
        self.lbl_temp.setFont(value_font)
        self.lbl_temp.setStyleSheet("color: #D84315;") 
        self.lbl_temp.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid_vals.addWidget(QLabel("Temperature:", font=title_font), 0, 0)
        grid_vals.addWidget(self.lbl_temp, 0, 1)

        # Hum
        self.lbl_hum = QLabel("--.- %")
        self.lbl_hum.setFont(value_font)
        self.lbl_hum.setStyleSheet("color: #1565C0;") 
        self.lbl_hum.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid_vals.addWidget(QLabel("Humidity:", font=title_font), 0, 2)
        grid_vals.addWidget(self.lbl_hum, 0, 3)

        # Gas
        self.lbl_gas = QLabel("---")
        self.lbl_gas.setFont(value_font)
        self.lbl_gas.setStyleSheet("color: #2E7D32;") 
        self.lbl_gas.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid_vals.addWidget(QLabel("AQI:", font=title_font), 0, 4)
        grid_vals.addWidget(self.lbl_gas, 0, 5)
        
        group_vals.setLayout(grid_vals)
        layout.addWidget(group_vals)

        # 2. Блок Графіків (Plotters)
        group_plots = QGroupBox("Real-time Plotter")
        plot_layout = QVBoxLayout()
        
        # Налаштування стилю pyqtgraph (білий фон)
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')

        # Графік температури
        self.plot_w_temp = pg.PlotWidget(title="Temperature (°C)")
        self.plot_w_temp.showGrid(x=True, y=True)
        self.curve_temp = self.plot_w_temp.plot(pen=pg.mkPen('#D84315', width=2)) # Червоний
        plot_layout.addWidget(self.plot_w_temp)

        # Графік вологості
        self.plot_w_hum = pg.PlotWidget(title="Humidity (%)")
        self.plot_w_hum.showGrid(x=True, y=True)
        self.curve_hum = self.plot_w_hum.plot(pen=pg.mkPen('#1565C0', width=2)) # Синій
        plot_layout.addWidget(self.plot_w_hum)

        # Графік газу
        self.plot_w_gas = pg.PlotWidget(title="Air quality index")
        self.plot_w_gas.showGrid(x=True, y=True)
        self.curve_gas = self.plot_w_gas.plot(pen=pg.mkPen('#2E7D32', width=2)) # Зелений
        plot_layout.addWidget(self.plot_w_gas)

        group_plots.setLayout(plot_layout)
        layout.addWidget(group_plots)

        # 3. Кнопка експорту
        self.btn_save = QPushButton("💾 Save Data to CSV (Excel)")
        self.btn_save.setFixedHeight(40)
        self.btn_save.setStyleSheet("font-size: 14px; font-weight: bold; background-color: #eee;")
        self.btn_save.clicked.connect(self.save_data_to_csv)
        layout.addWidget(self.btn_save)

        self.setLayout(layout)

        # --- Logic Setup ---
        self._log_config = None
        self._helper.cf.connected.add_callback(self._connected_cb)
        self._helper.cf.disconnected.add_callback(self._disconnected_cb)

    def _connected_cb(self, link_uri):
        # Очищаємо старі дані при новому підключенні
        self.data_storage = []
        self.ptr = 0
        self.buf_temp = [0.0] * self.buffer_size
        self.buf_hum = [0.0] * self.buffer_size
        self.buf_gas = [0.0] * self.buffer_size
        
        self.setup_log_config()

    def _disconnected_cb(self, link_uri):
        self.lbl_temp.setText("--.-")
        self.lbl_hum.setText("--.-")
        self.lbl_gas.setText("---")

    def setup_log_config(self):
        self._log_config = LogConfig(name='NiclaMonitor', period_in_ms=100)
        self._log_config.add_variable('nicla.temp', 'float')
        self._log_config.add_variable('nicla.hum', 'float')
        self._log_config.add_variable('nicla.gas', 'float')

        self._log_config.data_received_cb.add_callback(self._data_received)
        self._log_config.error_cb.add_callback(self._log_error)

        try:
            self._helper.cf.log.add_config(self._log_config)
            if self._log_config.valid:
                self._log_config.start()
        except KeyError:
            print("NiclaTab: Variables not found")

    def _data_received(self, timestamp, data, logconf):
        """Отримання даних від дрона"""
        t = data.get('nicla.temp', 0)
        h = data.get('nicla.hum', 0)
        g = data.get('nicla.gas', 0)
        
        # 1. Оновлення числових значень
        self.lbl_temp.setText(f"{t:.1f} °C")
        self.lbl_hum.setText(f"{h:.1f} %")
        self.lbl_gas.setText(f"{g:.0f}")

        # 2. Збереження в "довгу" пам'ять (для CSV)
        # Timestamp приходить в мс
        self.data_storage.append({
            'time': timestamp,
            'temp': t,
            'hum': h,
            'gas': g
        })

        # 3. Оновлення графіків (біжуче вікно)
        # Зсуваємо масив вліво і додаємо нове значення в кінець
        self.buf_temp[:-1] = self.buf_temp[1:]
        self.buf_temp[-1] = t
        
        self.buf_hum[:-1] = self.buf_hum[1:]
        self.buf_hum[-1] = h
        
        self.buf_gas[:-1] = self.buf_gas[1:]
        self.buf_gas[-1] = g
        
        self.ptr += 1

        # Оновлюємо лінії (перемальовуємо)
        self.curve_temp.setData(self.buf_temp)
        self.curve_hum.setData(self.buf_hum)
        self.curve_gas.setData(self.buf_gas)

    def save_data_to_csv(self):
        """Функція збереження таблиці"""
        if not self.data_storage:
            QMessageBox.warning(self, "No Data", "No data recorded yet to save.")
            return

        # Генеруємо ім'я файлу з датою
        default_name = f"nicla_flight_data_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Відкриваємо діалог збереження
        file_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", default_name, "CSV Files (*.csv)")
        
        if file_path:
            try:
                with open(file_path, mode='w', newline='') as file:
                    writer = csv.writer(file)
                    # Заголовок
                    writer.writerow(["Timestamp (ms)", "Temperature (C)", "Humidity (%)", "Gas Index"])
                    
                    # Дані
                    for row in self.data_storage:
                        writer.writerow([row['time'], row['temp'], row['hum'], row['gas']])
                
                QMessageBox.information(self, "Success", f"Saved {len(self.data_storage)} rows to:\n{file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")

    def _log_error(self, logconf, msg):
        print(f"Log Error: {msg}")

    def closeEvent(self, event):
        if self._log_config:
            self._log_config.stop()