import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def create_3d_box(dimensions, rotation_angles=(0, 0, 0), scale=1.0):
    """
    Creates a 3D box with specified dimensions and rotation angles.

    Args:
        dimensions: A tuple (length, width, height) representing the box dimensions.
        rotation_angles: A tuple (x_angle, y_angle, z_angle) representing rotation in degrees.
        scale: A float representing the scaling factor for the box.

    Returns:
        vertices: A numpy array of the box's vertices.
        edges: A list of edge indices.
    """

    length, width, height = dimensions
    length *= scale
    width *= scale
    height *= scale

    # Define the vertices of the box
    vertices = np.array([
        [0, 0, 0],
        [length, 0, 0],
        [length, width, 0],
        [0, width, 0],
        [0, 0, height],
        [length, 0, height],
        [length, width, height],
        [0, width, height]
    ])

    # Define the edges of the box
    edges = [
        [0, 1], [1, 2], [2, 3], [3, 0],
        [4, 5], [5, 6], [6, 7], [7, 4],
        [0, 4], [1, 5], [2, 6], [3, 7]
    ]

    # Rotate the box
    rx, ry, rz = np.radians(rotation_angles)  # Convert to radians

    # Rotation matrices
    Rx = np.array([
        [1, 0, 0],
        [0, np.cos(rx), -np.sin(rx)],
        [0, np.sin(rx), np.cos(rx)]
    ])
    Ry = np.array([
        [np.cos(ry), 0, np.sin(ry)],
        [0, 1, 0],
        [-np.sin(ry), 0, np.cos(ry)]
    ])
    Rz = np.array([
        [np.cos(rz), -np.sin(rz), 0],
        [np.sin(rz), np.cos(rz), 0],
        [0, 0, 1]
    ])

    # Apply rotations
    for i in range(len(vertices)):
        vertices[i] = np.dot(Rx, vertices[i])
        vertices[i] = np.dot(Ry, vertices[i])
        vertices[i] = np.dot(Rz, vertices[i])

    return vertices, edges


def plot_3d_box(vertices, edges, dimensions, scale=1.0):
    """Plots the 3D box with labels, scale lines, and dotted lines."""

    length, width, height = dimensions
    length *= scale
    width *= scale
    height *= scale

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    # Plot the edges of the box
    for edge in edges:
        ax.plot(vertices[edge, 0], vertices[edge, 1], vertices[edge, 2], color='black')

    # Plot dotted lines for back edges (example - adjust as needed)
    for edge in [[0, 2], [1, 3], [4, 6], [5, 7]]:
        ax.plot(vertices[edge, 0], vertices[edge, 1], vertices[edge, 2], color='gray', linestyle=':')

    # Scale lines and labels
    ax.plot([0, length], [0, 0], [0, 0], color='red')
    ax.text(length / 2, 0, 0, f'{length:.2f} cm', color='red', fontsize=12)

    ax.plot([0, 0], [0, width], [0, 0], color='green')
    ax.text(0, width / 2, 0, f'{width:.2f} cm', color='green', fontsize=12)

    ax.plot([0, 0], [0, 0], [0, height], color='blue')
    ax.text(0, 0, height / 2, f'{height:.2f} cm', color='blue', fontsize=12)

    # Set axis limits
    max_dim = max(length, width, height)
    ax.set_xlim([0, max_dim * 1.2])  # Add some padding
    ax.set_ylim([0, max_dim * 1.2])
    ax.set_zlim([0, max_dim * 1.2])

    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')

    plt.title('3D Box')
    plt.grid(False)  # Turn off grid
    ax.view_init(elev=20., azim=-35)  # Adjust view angle as needed
    plt.show()


# Example usage:
dimensions = (67, 41, 36)  # Length, width, height in cm
rotation_angles = (10, 20, 15)  # Rotation angles (x, y, z) in degrees
scale = 1.0  # You can change the scale if needed

vertices, edges = create_3d_box(dimensions, rotation_angles, scale)
plot_3d_box(vertices, edges, dimensions, scale)