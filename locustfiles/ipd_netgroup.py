from locust import HttpUser, task, between
from common.auth import Auth
import json
import random


class NetgroupAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    netgroups = None
    netgroup_created = False

    def on_start(self):
        """
        Retrieve auth token at startup
        """
        self.token = Auth.get_token(self)

    @task
    def post_netgroup(self):
        """
        POST /netgroups/
        """
        # Limite la création à 1 groupe par user Locust
        if self.netgroup_created:
            return

        if self.token:
            # Generate random num between 001 and 999
            random_number = f"{random.randint(1, 999):03}"

            # Data preparation with dynamic incrementation
            data = {
                "name": f"Network Group-{random_number}",
                "description": "Dummy network group description",
            }

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/netgroups/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(data),
            )

            if response.status_code not in (200, 201):
                print(
                    "An error occured when attempt to POST netgroup : ", response.text
                )
            else:
                # Marque qu'un groupe a déjà été créé pour ce user
                self.netgroup_created = True

        else:
            print("Token not available, request not executed")
