import tkinter as tk
import math

class RotatingBox(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("3D Box Viewer")
        self.geometry("800x600")
        
        self.canvas = tk.Canvas(self, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Box dimensions (relative)
        self.x_len = 36  # in cm
        self.y_len = 67  # in cm
        self.z_len = 41  # in cm
        
        # Initial rotation angles
        self.x_rot = -35  # in degrees
        self.y_rot = 20  # in degrees
        self.z_rot = 90  # in degrees
        
        # Bind resize event
        self.bind("<Configure>", self.on_resize)
        
        # Initial draw
        self.update_box()
    
    def on_resize(self, event):
        self.update_box()
    
    def update_box(self):
        center_x = self.canvas.winfo_width() // 2
        center_y = self.canvas.winfo_height() // 2
        canvas_height = self.canvas.winfo_height()
        available_height = canvas_height - 40  # Padding of 20 on each side

        max_dimension = max(self.x_len, self.y_len, self.z_len)
        scale = available_height / max_dimension  # Ensures full utilization of space  # Ensures full vertical fit
        
        create_3d_box(self.canvas, self.x_len, self.y_len, self.z_len,
                     self.x_rot, self.y_rot, self.z_rot, center_x, center_y, scale)

def create_3d_box(canvas, x_len, y_len, z_len, x_rot, y_rot, z_rot, center_x, center_y, scale):
    """ Draws a 3D box on a canvas using rotation and projection."""
    
    corners_3d = [
        (-x_len/2, -y_len/2, -z_len/2), (x_len/2, -y_len/2, -z_len/2),
        (x_len/2, y_len/2, -z_len/2), (-x_len/2, y_len/2, -z_len/2),
        (-x_len/2, -y_len/2, z_len/2), (x_len/2, -y_len/2, z_len/2),
        (x_len/2, y_len/2, z_len/2), (-x_len/2, y_len/2, z_len/2)
    ]
    
    def rotate_point(point, x_rot, y_rot, z_rot):
        x, y, z = point
        
        # X-axis rotation
        y, z = (y * math.cos(math.radians(x_rot)) - z * math.sin(math.radians(x_rot)),
                y * math.sin(math.radians(x_rot)) + z * math.cos(math.radians(x_rot)))
        
        # Y-axis rotation
        x, z = (x * math.cos(math.radians(y_rot)) + z * math.sin(math.radians(y_rot)),
                -x * math.sin(math.radians(y_rot)) + z * math.cos(math.radians(y_rot)))
        
        # Z-axis rotation
        x, y = (x * math.cos(math.radians(z_rot)) - y * math.sin(math.radians(z_rot)),
                x * math.sin(math.radians(z_rot)) + y * math.cos(math.radians(z_rot)))
        
        return x, y, z
    
    def project_point(point):
        x, y, z = point
        factor = 200 / (z + 400)  # Perspective factor
        return (factor * x * scale + center_x, factor * y * scale + center_y)
    
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    
    canvas.delete("all")
    
    for edge in edges:
        p1_proj = project_point(rotate_point(corners_3d[edge[0]], x_rot, y_rot, z_rot))
        p2_proj = project_point(rotate_point(corners_3d[edge[1]], x_rot, y_rot, z_rot))
        if p1_proj and p2_proj:
            canvas.create_line(p1_proj, p2_proj, dash=(5, 5))  # Dotted lines

    # Add dimension labels
    label_positions = [(1, 4, x_len), (0, 3, y_len), (0, 4, z_len)]
    for edge in label_positions:
        mid_x = (corners_3d[edge[0]][0] + corners_3d[edge[1]][0]) / 2
        mid_y = (corners_3d[edge[0]][1] + corners_3d[edge[1]][1]) / 2
        mid_z = (corners_3d[edge[0]][2] + corners_3d[edge[1]][2]) / 2
        proj_x, proj_y = project_point(rotate_point((mid_x, mid_y, mid_z), x_rot, y_rot, z_rot))
        canvas.create_text(proj_x + 10, proj_y + 10, text=f'{edge[2]}cm', font=("Arial", 9))

if __name__ == "__main__":
    app = RotatingBox()
    app.mainloop()
