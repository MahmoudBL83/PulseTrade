import sys
from PyQt5.QtWidgets import QMainWindow, QApplication, QPushButton, QVBoxLayout, QWidget, QLabel, QColorDialog, \
    QHBoxLayout
import numpy as np
from matplotlib.animation import FuncAnimation

from pyqtgraph import PlotWidget

class SignalViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set up the main UI layout
        self.setWindowTitle("Multi-Channel Signal Viewer")
        self.setGeometry(100, 100, 1000, 800)

        # Main Widget
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        layout = QVBoxLayout(self.main_widget)

        # Graph 1
        self.graph1_label = QLabel("Cine Mode Signal (Graph 1)")
        layout.addWidget(self.graph1_label)
        self.graph1_canvas = PlotWidget()
        layout.addWidget(self.graph1_canvas)

        # Graph 2
        self.graph2_label = QLabel("Cine Mode Signal (Graph 2)")
        layout.addWidget(self.graph2_label)
        self.graph2_canvas = PlotWidget()
        layout.addWidget(self.graph2_canvas)

        # Buttons for controlling the signals
        self.controls_layout = QHBoxLayout()

        # Start Button
        self.start_button = self.create_styled_button('Start Animation')
        self.controls_layout.addWidget(self.start_button)
        self.start_button.clicked.connect(self.start_animation)

        # Pause/Resume Button
        self.pause_button = self.create_styled_button('Pause')
        self.controls_layout.addWidget(self.pause_button)
        self.pause_button.clicked.connect(self.pause_animation)

        # Speed Control Buttons
        self.increase_speed_button = self.create_styled_button('Increase Speed')
        self.controls_layout.addWidget(self.increase_speed_button)
        self.increase_speed_button.clicked.connect(self.increase_speed)

        self.decrease_speed_button = self.create_styled_button('Decrease Speed')
        self.controls_layout.addWidget(self.decrease_speed_button)
        self.decrease_speed_button.clicked.connect(self.decrease_speed)

        # Rewind Button
        self.rewind_button = self.create_styled_button('Rewind')
        self.controls_layout.addWidget(self.rewind_button)
        self.rewind_button.clicked.connect(self.rewind_animation)

        # Change Color Button
        self.change_color_button = self.create_styled_button('Change Color')
        self.controls_layout.addWidget(self.change_color_button)
        self.change_color_button.clicked.connect(self.change_color)

        # Move signal buttons
        self.move_to_graph2_button = self.create_styled_button('Move to Graph 2')
        self.controls_layout.addWidget(self.move_to_graph2_button)
        self.move_to_graph2_button.clicked.connect(self.move_to_graph2)

        self.move_to_graph1_button = self.create_styled_button('Move to Graph 1')
        self.controls_layout.addWidget(self.move_to_graph1_button)
        self.move_to_graph1_button.clicked.connect(self.move_to_graph1)

        layout.addLayout(self.controls_layout)

        # Animation parameters
        self.anim1 = None
        self.anim2 = None
        self.speed = 1  # Initial speed
        self.is_paused = False

        # Dummy signal data
        self.time = np.linspace(0, 10, 1000)
        self.signal = np.sin(self.time)
        self.line1 = self.graph1_canvas.plot([], [], pen='b')
        self.line2 = self.graph2_canvas.plot([], [], pen='b')

        self.current_graph = 1  # Track which graph is active

    import sys
from PyQt5.QtWidgets import QMainWindow, QApplication, QPushButton, QVBoxLayout, QWidget, QLabel, QSlider, QColorDialog, QHBoxLayout
import pyqtgraph as pg
import numpy as np
from PyQt5.QtCore import QTimer

class SignalViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set up the main UI layout
        self.setWindowTitle("Multi-Channel Signal Viewer")
        self.setGeometry(100, 100, 1000, 800)

        # Main Widget
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        layout = QVBoxLayout(self.main_widget)

        # Graph 1
        self.graph1_label = QLabel("Cine Mode Signal (Graph 1)")
        layout.addWidget(self.graph1_label)
        self.graph1_widget = pg.PlotWidget()
        layout.addWidget(self.graph1_widget)
        self.graph1_curve = self.graph1_widget.plot(pen='b')

        # Graph 2
        self.graph2_label = QLabel("Cine Mode Signal (Graph 2)")
        layout.addWidget(self.graph2_label)
        self.graph2_widget = pg.PlotWidget()
        layout.addWidget(self.graph2_widget)
        self.graph2_curve = self.graph2_widget.plot(pen='b')

        # Buttons for controlling the signals
        self.controls_layout = QHBoxLayout()

        # Start Button
        self.start_button = self.create_styled_button('Start Animation')
        self.controls_layout.addWidget(self.start_button)
        self.start_button.clicked.connect(self.start_animation)

        # Pause/Resume Button
        self.pause_button = self.create_styled_button('Pause')
        self.controls_layout.addWidget(self.pause_button)
        self.pause_button.clicked.connect(self.pause_animation)

        # Speed Slider
        self.speed_slider = QSlider()
        self.speed_slider.setMinimum(1)
        self.speed_slider.setMaximum(40)
        self.speed_slider.setValue(1)  # Initial speed
        self.speed_slider.setOrientation(1)  # Horizontal
        self.controls_layout.addWidget(QLabel('Speed'))
        self.controls_layout.addWidget(self.speed_slider)

        # Rewind Button
        self.rewind_button = self.create_styled_button('Rewind')
        self.controls_layout.addWidget(self.rewind_button)
        self.rewind_button.clicked.connect(self.rewind_animation)

        # Change Color Button
        self.change_color_button = self.create_styled_button('Change Color')
        self.controls_layout.addWidget(self.change_color_button)
        self.change_color_button.clicked.connect(self.change_color)

        # Move signal buttons
        self.move_to_graph2_button = self.create_styled_button('Move to Graph 2')
        self.controls_layout.addWidget(self.move_to_graph2_button)
        self.move_to_graph2_button.clicked.connect(self.move_to_graph2)

        self.move_to_graph1_button = self.create_styled_button('Move to Graph 1')
        self.controls_layout.addWidget(self.move_to_graph1_button)
        self.move_to_graph1_button.clicked.connect(self.move_to_graph1)

        layout.addLayout(self.controls_layout)

        # Animation parameters
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.animating = False
        self.current_graph = 1  # Track which graph is active

        # Dummy signal data
        self.time = np.linspace(0, 10, 1000)
        self.signal = np.sin(self.time)
        self.current_index = 0

def update_plot(self):
    # Determine speed from slider
    speed = self.speed_slider.value()

    # Calculate the next set of points to plot
    end = self.current_index + speed
    if end >= len(self.time):
        end = len(self.time)
    
    if self.current_graph == 1:
        self.graph1_curve.setData(self.time[:end], self.signal[:end])
    else:
        self.graph2_curve.setData(self.time[:end], self.signal[:end])

    self.current_index = end
    if self.current_index == len(self.time):
        self.timer.stop()

def start_animation(self):
    if not self.animating:
        self.timer.start(50)
        self.animating = True

def pause_animation(animating,timer,pause_button):
    timer.stop()
    pause_button.setText("Resume")

def rewind_animation(timer,graph):
    timer.stop()  # Stop the current animation
    graph.clear()
    start_animation()

def change_color(self):
    color = QColorDialog.getColor()
    if self.current_graph == 1:
        self.graph1_curve.setPen(color.name())
    else:
        self.graph2_curve.setPen(color.name())

def move_to_graph2(self):
    self.current_graph = 2
    self.rewind_animation()

def move_to_graph1(self):
    self.current_graph = 1
    self.rewind_animation()


