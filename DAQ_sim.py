import numpy as np
import random
import sys
from collections import deque
import time
from enum import Enum

import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore, uic
from PyQt5.QtWidgets import (QApplication, QMainWindow,
                             QDialog, QTableWidget, QTableWidgetItem)
from PyQt5.QtCore import QTimer, QSize

#print(sys.platform)
if sys.platform == "win32":
    import ctypes
    ctypes.windll.winmm.timeBeginPeriod(1)

class Mode(Enum):
    '''
    Enum class specifying a data acquisition mode: dormant and waiting
    to be woken up (IDLE), live streaming data to display (MONITOR),
    and collecting/saving data to a file (RECORD).
    '''
    IDLE = 0
    MONITOR = 1
    RECORD = 2

class Parameters(Enum):
    '''Enum class for parameters used throughout the code.'''
    FPS = 30                # frames/second of the plot display
    DAQ_SPEED = 1            # data acquisition rate in milliseconds
    BUFFER_LEN = 1000       # number of data points in the live buffer

##print(Mode.__members__)
##print(Mode.IDLE.name)
##print(Mode.IDLE.value)


class SPMaster(QMainWindow):
    '''
    Main GUI thread using uic.loadUI(), grabbing the
    QtDesigner widgets. Widgets control the state of the data
    acquisition class called 'DAQThread', simulating experimental
    data monitoring in real time.
    '''
    def __init__(self):
        QMainWindow.__init__(self)
        uic.loadUi("live_DAQ_simulator.ui", self)

        self.plot_1.setTitle("Live Data Streaming", size="14pt")
        self.x_axis_1 = pg.AxisItem("bottom")
        self.x_axis_1.setLabel(text="Time", units="s")
        self.y_axis_1 = pg.AxisItem("left")
        self.y_axis_1.setLabel(text="Simulated acquisiton data",
                               units="a.u.")
        self.plot_1.setAxisItems({"bottom":self.x_axis_1,
                                  "left":self.y_axis_1})

        self.plot_2.setTitle("")
        self.x_axis_2 = pg.AxisItem("bottom")
        self.x_axis_2.setLabel(text="Time", units="s")
        self.y_axis_2 = pg.AxisItem("left")
        self.y_axis_2.setLabel(text="Instantaneous data rate",
                               units="samples/s")
        self.plot_2.setAxisItems({"bottom":self.x_axis_2,
                                  "left":self.y_axis_2})
        
        self.curve_1 = self.plot_1.plot()
        self.curve_2 = self.plot_2.plot()
        self.avg_curve_1 = self.plot_1.plot(pen="r")
        self.avg_curve_2 = self.plot_2.plot(pen="r")
        self.stddev_curve_1 = self.plot_1.plot(pen="b")
        self.stddev_curve_2 = self.plot_2.plot(pen="b")
        #print(self.plot_1.listDataItems())
        #print(self.plot_2.listDataItems())
        #print(self.curve_3 in self.plot_1.listDataItems())
        #print(self.curve_4 in self.plot_2.listDataItems())
        self.plot_1.show()
        self.plot_2.show()

        self.plot_timer = QtCore.QTimer()
        self.plot_timer.timeout.connect(self.update_plot)
        self.start_daq_thread()

        self.start_button.clicked.connect(
            lambda: self.daq.set_mode.emit(Mode.MONITOR)
            )
        self.stop_button.clicked.connect(
            lambda: self.daq.set_mode.emit(Mode.IDLE)
            )
        self.plot_button.clicked.connect(self.toggle_display)

        self.actionConnect_equipment.triggered.connect(self.connect_equipment)
        
    def connect_equipment(self):
        self.equipment_dialog = ConnectEquipment(self)
        self.equipment_dialog.exec_()

    def start_daq_thread(self) -> None:
        '''
        Creates an instance of the data acquisition thread
        object and starts the thread. In a real laboratory
        experiment, each instance would be a different piece
        of equipment for simultaneous live monitoring of
        different data channels.
        '''
        self.daq = DAQThread()
        self.daq.set_mode.connect(self.daq._set_mode)
        self.daq.set_mode.connect(self.button_state)
        self.daq.publish_snapshot.connect(self.daq._publish_snapshot)
        self.daq.start()

    @QtCore.pyqtSlot(object)
    def button_state(self, state: Mode) -> None:
        if state is Mode.MONITOR:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.plot_button.setEnabled(True)
        elif state is Mode.IDLE:
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.plot_button.setEnabled(False)
    
    def update_plot(self) -> None:
        self.daq.publish_snapshot.emit()
        self.daq.mutex.lock()
        plot_data = self.daq.published_snapshot
        self.daq.mutex.unlock()

        x1 = np.array([i[0] for i in plot_data])
        x1 = x1-min(x1)
        y1 = np.array([i[1] for i in plot_data])
        x2 = np.array([plot_data[i][0] for i in range(1,len(plot_data))])
        x2 = x2-min(x2)
        y2 = np.array([(1/(
            plot_data[i][0]-plot_data[i-1][0])
                        ) for i in range(1,len(plot_data))])
        
        avg_data_value = np.mean(y1)
        stddev_data_value = np.std(y1)
        avg_data_rate = len(plot_data)/max(x1)
        stddev_data_rate = np.std(y2)

        if self.average_cb_1.isChecked():
            x1_avg = np.copy(x2)
            y1_avg = np.array([avg_data_value for i in range(1,len(plot_data))])
            if self.avg_curve_1 in self.plot_1.listDataItems():
                self.avg_curve_1.setData(x1_avg, y1_avg)
            else:
                self.plot_1.addItem(self.avg_curve_1)
                self.avg_curve_1.setData(x1_avg, y1_avg)
        else:
            if self.avg_curve_1 in self.plot_1.listDataItems():
                self.plot_1.removeItem(self.avg_curve_1)

        if self.average_cb_2.isChecked():
            x2_avg = np.copy(x2)
            y2_avg = np.array([avg_data_rate for i in range(1,len(plot_data))])
            if self.avg_curve_2 in self.plot_2.listDataItems():
                self.avg_curve_2.setData(x2_avg, y2_avg)
            else:
                self.plot_2.addItem(self.avg_curve_2)
                self.avg_curve_2.setData(x2_avg, y2_avg)
        else:
            if self.avg_curve_2 in self.plot_2.listDataItems():
                self.plot_2.removeItem(self.avg_curve_2)

        if self.stddev_cb_1.isChecked():
            x1_stddev = np.copy(x2)
            y1_stddev = np.array([stddev_data_value for i in range(1,len(plot_data))])
            if self.stddev_curve_1 in self.plot_1.listDataItems():
                self.stddev_curve_1.setData(x1_stddev, y1_stddev)
            else:
                self.plot_1.addItem(self.stddev_curve_1)
                self.stddev_curve_1.setData(x1_stddev, y1_stddev)
        else:
            if self.stddev_curve_1 in self.plot_1.listDataItems():
                self.plot_1.removeItem(self.stddev_curve_1)

        if self.stddev_cb_2.isChecked():
            x2_stddev = np.copy(x2)
            y2_stddev = np.array([stddev_data_rate for i in range(1,len(plot_data))])
            if self.stddev_curve_2 in self.plot_2.listDataItems():
                self.stddev_curve_2.setData(x2_stddev, y2_stddev)
            else:
                self.plot_2.addItem(self.stddev_curve_2)
                self.stddev_curve_2.setData(x2_stddev, y2_stddev)
        else:
            if self.stddev_curve_2 in self.plot_2.listDataItems():
                self.plot_2.removeItem(self.stddev_curve_2)

        self.curve_1.setData(x1,y1)
        self.curve_2.setData(x2,y2)
        
        self.data_len_label.setText(str(len(plot_data)))
        self.avg_data_rate_label.setText(str(int(avg_data_rate))+" samples/s")


    def toggle_display(self) -> None:
        if self.plot_button.text() == "PLOT":
            self.plot_timer.start(int(1000/Parameters.FPS.value))
            self.plot_button.setText("STOP")
        else:
            self.plot_timer.stop()
            self.plot_button.setText("PLOT")

    def closeEvent(self, event):
        print("FINISHED", event)


class DAQThread(QtCore.QThread):
    '''
    Data acquisition thread simulation designed for
    testing computer interfacing with laboratory equipment.
    '''
    set_mode = QtCore.pyqtSignal(object)
    publish_snapshot = QtCore.pyqtSignal()
    def __init__(self):
        super().__init__()
        self.mode = Mode.IDLE
        self.mutex = QtCore.QMutex()
        self.wait = QtCore.QWaitCondition()
        self.live_buffer = deque(maxlen=Parameters.BUFFER_LEN.value)
        self.published_snapshot = None

    def run(self) -> None:
        '''
        Runs once the thread is started with the
        thread.start() method. This function is not
        explicitly called.
        '''
        while True:
            self.mutex.lock()
            if self.mode is Mode.IDLE:
                self.wait.wait(self.mutex)
            self.mutex.unlock()
            
            v = random.randrange(100)/100
            t = time.perf_counter()
            self.live_buffer.append((t,v))

            self.msleep(Parameters.DAQ_SPEED.value)

    @QtCore.pyqtSlot(object)
    def _set_mode(self, mode) -> None:
        self.mutex.lock()
        self.mode = mode
        if self.mode is Mode.MONITOR:
            self.wait.wakeAll()
        self.mutex.unlock()

    @QtCore.pyqtSlot()
    def _publish_snapshot(self) -> None:
        snapshot = list(self.live_buffer)

        self.mutex.lock()
        self.published_snapshot = snapshot
        self.mutex.unlock()

class ConnectEquipment(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        uic.loadUi("equipment_dialog.ui", self)

        equipment_list = [("Lockin", "USB::EQUIPMENT::TAG1","Connected"),
                          ("Oscilloscope", "USB::EQUIPMENT::TAG2","Disconnected")]
        table = self.tableWidget
        table.setRowCount(len(equipment_list))
        table.setColumnCount(len(equipment_list[0]))
        table.setHorizontalHeaderLabels(["Name", "Visa tag", "Status"])

        for i, (name, tag, status) in enumerate(equipment_list):
            _name = QTableWidgetItem(name)
            _tag = QTableWidgetItem(tag)
            _status = QTableWidgetItem(status)
            table.setItem(i, 0, _name)
            table.setItem(i, 1, _tag)
            table.setItem(i, 2, _status)

        table.resizeRowsToContents()
        table.resizeColumnsToContents()
        table.show()
        


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SPMaster()
    win.show()
    sys.exit(app.exec_())
