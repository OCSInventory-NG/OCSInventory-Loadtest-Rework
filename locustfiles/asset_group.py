from locust import HttpUser, task, between
from common.auth import Auth
import json
import random


class AssetGroupAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None

    def on_start(self):
        # Retrieve auth token at startup
        self.token = Auth.get_token(self)

    @task
    def create_group(self):
        """
        POST /groups
        """
        if self.token:
            # Generate random num between 00001 and 99999
            random_number = f"{random.randint(1, 99999):05}"
            # Data preparation with dynamic incrementation
            data = {
                "name": f"Dummy-Group-{random_number}",
                "permissions": [
                    13,
                    14,
                    15,
                    16,
                    25,
                    26,
                    27,
                    28,
                    29,
                    30,
                    31,
                    32,
                    21,
                    22,
                    23,
                    24,
                ],
            }

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/groups/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(data),
            )

            if response.status_code != 200:
                print(
                    "An error occured when attempt to POST asset base : ", response.text
                )

        else:
            print("Token not available, request not executed")
