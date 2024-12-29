clear
locust -f mocking/locustfile.py --host=http://localhost:8080 -u 10 --run-time 300s