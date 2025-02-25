import numpy as np
import svgwrite

def generate_box_svg(width, height, length, filename="box_outline.svg"):
    # [Previous box corner and rotation code remains the same until the drawing part]
    corners = np.array([
        [0, 0, 0],               # Bottom-front-left
        [width, 0, 0],           # Bottom-front-right
        [width, length, 0],      # Bottom-back-right
        [0, length, 0],          # Bottom-back-left
        [0, 0, height],          # Top-front-left
        [width, 0, height],      # Top-front-right
        [width, length, height], # Top-back-right
        [0, length, height]      # Top-back-left
    ])

    angle_y_rad = np.radians(150)
    rotation_y = np.array([
        [np.cos(angle_y_rad),  0, np.sin(angle_y_rad)],
        [0,                    1, 0],
        [-np.sin(angle_y_rad), 0, np.cos(angle_y_rad)]
    ])

    angle_x_rad = np.radians(20)
    rotation_x = np.array([
        [1, 0,                   0],
        [0, np.cos(angle_x_rad), -np.sin(angle_x_rad)],
        [0, np.sin(angle_x_rad),  np.cos(angle_x_rad)]
    ])

    rotated_corners = corners @ rotation_y.T @ rotation_x.T
    projected_corners = rotated_corners[:, :2]

    min_x = np.min(projected_corners[:, 0])
    max_x = np.max(projected_corners[:, 0])
    min_y = np.min(projected_corners[:, 1])
    max_y = np.max(projected_corners[:, 1])
    
    box_width = max_x - min_x
    box_height = max_y - min_y

    canvas_size = 800
    dwg = svgwrite.Drawing(filename, size=(f"{canvas_size}px", f"{canvas_size}px"), profile='tiny')
    
    padding = canvas_size * 0.1
    
    scale_x = (canvas_size - 2 * padding) / box_width
    scale_y = (canvas_size - 2 * padding) / box_height
    scale = min(scale_x, scale_y)
    
    center_x = canvas_size/2 - (min_x + box_width/2) * scale
    center_y = canvas_size/2 + (min_y + box_height/2) * scale

    # Create groups for different elements
    box_group = dwg.g()
    scale_group = dwg.g()

    # Draw measurement scales first (they should be behind the box)
    # Get corner points for scale positioning
    bl = (center_x + scale * projected_corners[0][0], center_y - scale * projected_corners[0][1])
    br = (center_x + scale * projected_corners[1][0], center_y - scale * projected_corners[1][1])
    fr = (center_x + scale * projected_corners[2][0], center_y - scale * projected_corners[2][1])
    fl = (center_x + scale * projected_corners[4][0], center_y - scale * projected_corners[4][1])

    # Scale line style
    scale_color = "#FF69B4"  # Pink color
    scale_width = 1
    extension = 20  # How far the scale lines extend beyond the box

    # Draw width scale (bottom)
    scale_group.add(dwg.line(
        start=(bl[0], bl[1] + extension),
        end=(br[0], br[1] + extension),
        stroke=scale_color,
        stroke_width=scale_width,
        stroke_dasharray="4,4"
    ))
    
    # Draw height scale (right)
    scale_group.add(dwg.line(
        start=(br[0] + extension, br[1]),
        end=(br[0] + extension, fl[1]),
        stroke=scale_color,
        stroke_width=scale_width,
        stroke_dasharray="4,4"
    ))

    # Draw length scale (left/back)
    scale_group.add(dwg.line(
        start=(bl[0] - extension, bl[1]),
        end=(bl[0] - extension, fl[1]),
        stroke=scale_color,
        stroke_width=scale_width,
        stroke_dasharray="4,4"
    ))

    # Draw end caps for scales
    cap_length = 5
    
    # Width scale caps
    scale_group.add(dwg.line(
        start=(bl[0], bl[1] + extension - cap_length),
        end=(bl[0], bl[1] + extension + cap_length),
        stroke=scale_color,
        stroke_width=scale_width
    ))
    scale_group.add(dwg.line(
        start=(br[0], br[1] + extension - cap_length),
        end=(br[0], br[1] + extension + cap_length),
        stroke=scale_color,
        stroke_width=scale_width
    ))

    # Height scale caps
    scale_group.add(dwg.line(
        start=(br[0] + extension - cap_length, br[1]),
        end=(br[0] + extension + cap_length, br[1]),
        stroke=scale_color,
        stroke_width=scale_width
    ))
    scale_group.add(dwg.line(
        start=(br[0] + extension - cap_length, fl[1]),
        end=(br[0] + extension + cap_length, fl[1]),
        stroke=scale_color,
        stroke_width=scale_width
    ))

    # Length scale caps
    scale_group.add(dwg.line(
        start=(bl[0] - extension - cap_length, bl[1]),
        end=(bl[0] - extension + cap_length, bl[1]),
        stroke=scale_color,
        stroke_width=scale_width
    ))
    scale_group.add(dwg.line(
        start=(bl[0] - extension - cap_length, fl[1]),
        end=(bl[0] - extension + cap_length, fl[1]),
        stroke=scale_color,
        stroke_width=scale_width
    ))

    # Draw the box
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # Bottom face
        (4, 5), (5, 6), (6, 7), (7, 4),  # Top face
        (0, 4), (1, 5), (2, 6), (3, 7)   # Vertical edges
    ]
    back_edges = {(2, 3), (2, 6), (6, 7), (3, 7)}
    
    for edge in edges:
        start = projected_corners[edge[0]]
        end = projected_corners[edge[1]]
        
        line = dwg.line(
            start=(center_x + scale * start[0], center_y - scale * start[1]),
            end=(center_x + scale * end[0], center_y - scale * end[1]),
            stroke=svgwrite.rgb(0, 255, 255, '%'),
            stroke_width=1.5
        )
        
        if edge in back_edges:
            line['stroke-dasharray'] = '4,4'
            
        box_group.add(line)

    # Add labels
    font_size = 20
    font_family = 'Arial, sans-serif'
    
    def create_label(text, x, y):
        label = dwg.text(text, insert=(x, y), fill=scale_color,
                        font_size=font_size, font_family=font_family)
        return label

    # Width label
    box_group.add(create_label(f"{width} cm", bl[0] + (br[0] - bl[0])/2 - 30, bl[1] + font_size * 1.5))

    # Height label
    box_group.add(create_label(f"{height} cm", br[0] + font_size/2, br[1] - (fl[1] - bl[1])/2))

    # Length label
    box_group.add(create_label(f"{length} cm", bl[0] + font_size/2, bl[1] - (fl[1] - bl[1])/2))

    # Add all elements to the drawing in the correct order
    dwg.add(scale_group)  # Scales go behind
    dwg.add(box_group)    # Box and labels go in front

    dwg.save()
    print(f"SVG saved as {filename}")

# Use with the dimensions from the image
generate_box_svg(width=67, height=36, length=41)