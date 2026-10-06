# button_functions.py
from PyQt5.QtWidgets import QColorDialog

def increase_speed(timer):
    current_interval = timer.interval()  # Get the current interval in milliseconds
    if current_interval > 100:  # Prevent it from going too fast
        new_interval = max(100, current_interval - 100)  # Decrease the interval to make it faster
        timer.setInterval(new_interval)
        print(f"Speed increased. New interval: {new_interval} ms")

def decrease_speed(timer):
    current_interval = timer.interval()  # Get the current interval in milliseconds
    new_interval = current_interval + 100  # Increase the interval to make it slower
    timer.setInterval(new_interval)
    print(f"Speed decreased. New interval: {new_interval} ms")



def start_simulation(timer):
    """Starts the simulation by starting the timer."""
    if not timer.isActive():
        timer.start()

def stop_simulation(timer):
    """Stops the simulation by stopping the timer."""
    if timer.isActive():
        timer.stop()

def rewind(timer, time_index, graph):
    """Rewind the time index to the beginning."""
    # clear the graph
    graph.clear()
    if timer.isActive():
        timer.stop()  # Stop the timer if it's running
    time_index = 0  # Reset the time index to the beginning
    print("Simulation rewound to start.")

    # Start the simulation again from the beginning
    timer.start()
    print("Simulation started from the beginning.")
    return time_index

def zoom_in(graph_widget):
    """Zooms in on the graph by increasing the view range."""
    view_range = graph_widget.viewRange()
    graph_widget.setXRange(view_range[0][0] + 1, view_range[0][1] - 1, padding=0)
    graph_widget.setYRange(view_range[1][0] + 1, view_range[1][1] - 1, padding=0)

def zoom_out(graph_widget):
    """Zooms out on the graph by decreasing the view range."""
    view_range = graph_widget.viewRange()
    graph_widget.setXRange(view_range[0][0] - 1, view_range[0][1] + 1, padding=0)
    graph_widget.setYRange(view_range[1][0] - 1, view_range[1][1] + 1, padding=0)

def hide_graph(graph_widget):
    """Hides the graph by setting it invisible."""
    graph_widget.hide()

def show_graph(graph_widget):
    """Shows the graph by setting it visible."""
    graph_widget.show()


def change_color(graph):
    # open a color dialog to choose a color
    color = QColorDialog.getColor()
    if color.isValid():
        # change the background color of the graph
        graph.setBackground(color)


    
def adjust_graph_1_slider_max(self):
    """Adjusts the maximum value of the graph 1 horizontal slider based on signal length."""
    if self.signal_data1 is not None:
        total_length = len(self.signal_data1[0])  # Assuming signal_data1 is 2D
        window_size = 100  # Adjust as needed
        max_slider_value = total_length - window_size
        
        # Set the slider maximum dynamically
        self.graph_1_H_slider.setMaximum(max_slider_value)

def adjust_graph_2_slider_max(self):
    """Adjusts the maximum value of the graph 2 horizontal slider based on signal length."""
    if self.signal_data2 is not None:
        total_length = len(self.signal_data2[0])  # Assuming signal_data2 is 2D
        window_size = 100  # Adjust as needed
        max_slider_value = total_length - window_size
        
        # Set the slider maximum dynamically
        self.graph_2_H_slider.setMaximum(max_slider_value)
