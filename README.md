# OCSInventory-Loadtest-Rework

## Prerequisite

Install the requirements with :

```
pip3 install -r requirements.txt
```

## Configuration

_locust.conf_
```
# Locust test files folder
locustfile = locustfiles/
# Run without UI
headless = true
# API host
host = http://172.18.25.201:8000
# Number of test users
users = 1
# Spawn rate in second
spawn-rate = 10
# Test run time
run-time = 10m
```

## Launch test

```
cd OCSInventory-Loadtest-Rework
locust --config locust.conf
```

For more information, see [Locust documentation](https://docs.locust.io/en/stable/index.html).

