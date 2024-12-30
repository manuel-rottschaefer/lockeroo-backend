clear
locust -f mocking/locustfile.py --host=http://localhost:8080 -u 10 -r 0.1 --run-time 600s