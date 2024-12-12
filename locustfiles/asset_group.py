from locust import HttpUser, task, between
from common.auth import Auth
import json
import random


class AssetGroupAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    search = None
    assets = []

    def on_start(self):
        # Retrieve auth token at startup
        self.token = Auth.get_token(self)

    @task
    def create_group(self):
        """
        POST /asset/groups
        """
        if self.token:
            # Generate random num between 00001 and 99999
            random_number = f"{random.randint(1, 99999):05}"

            self.search = [
                [
                    {
                        "link": "",
                        "field": "name",
                        "route": "asset/bases",
                        "value": "PC",
                        "object": "InventoryBase",
                        "operator": "istartswith",
                        "fieldtype": "string",
                    }
                ]
            ]

            self.get_assets()

            # Data preparation with dynamic incrementation
            data = {
                "visibility": "public",
                "allow_group_modification": False,
                "name": f"Dummy group {random_number}",
                "description": "Dummy group",
                "is_dynamic": True,
                "search": self.search,
                "user": 1,
                "groups": [],
                "assets": self.assets,
            }

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/asset/groups/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(data),
            )

            if response.status_code != 200:
                print(
                    "An error occured when attempt to POST asset group : ",
                    response.text,
                )

        else:
            print("Token not available, request not executed")

    def get_assets(self):
        """
        GET /search
        """
        if self.token:
            # Sending the POST request with the authentication token
            response = self.client.post(
                "/search/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(self.search),
            )

            if response.status_code == 200:
                assets = response.json()
                for asset in assets:
                    self.assets.append(asset.get("pk"))
            else:
                print(
                    "An error occured when attempt to retrieve assets : ",
                    response.text,
                )
        else:
            print("Token not available, request not executed")
