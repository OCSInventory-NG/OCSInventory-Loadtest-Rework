from locust import HttpUser, task, between
from common.auth import Auth
import json
import random

class AssetBaseAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    os_options = ["windows", "linux", "mac"]

    def on_start(self):
        # Retrieve auth token at startup
        self.token = Auth.get_token(self)

    @task
    def create_asset(self):
        if self.token:
            # Generate random num between 0001 and 9999
            random_number = f"{random.randint(1, 9999):04}"
            # Random selection of an operating system for osname
            osname = random.choice(self.os_options)

            # Data preparation with dynamic incrementation
            data = {
                "name": f"PC-{random_number}",
                "description": "Dummy Computer System Product for API test",
                "serial": f"00000-00000-00000-0{random_number}",
                "osname": osname,
                "osversion": "1.0.0",
                "uuid": f"DUMMY-UUID{random_number}",
                "srcip": "127.0.0.1",
                "srcmac": "XX-XX-XX-XX-XX-XX",
                "domain": "WORKGROUP",
                "template": None
            }

            # Sending the POST request with the authentication token
            self.client.post(
                "/asset/bases/",
                headers={"Authorization": f"Token {self.token}", "Content-Type": "application/json"},
                data=json.dumps(data)
            )

        else:
            print("Token not available, request not executed")