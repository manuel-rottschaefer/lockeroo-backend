locust -f mocking/locustfile.py --host=http://localhost:8080 -u 16 -r 0.2 #--run-time 600s --autostart --json > mocking/results.json
