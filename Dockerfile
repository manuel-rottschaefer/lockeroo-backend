# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install locust

# Make port 8089 available to the world outside this container
EXPOSE 8080

# Run main.py when the container launches
CMD ["python3", "main.py"]