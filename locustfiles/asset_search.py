from locust import HttpUser, task, between
from common.auth import Auth
import json


class AssetSearchAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    assets = None

    def on_start(self):
        # Retrieve auth token at startup
        self.token = Auth.get_token(self)

    @task
    def simple_base_request(self):
        if not self.token:
            print("Token not available, request not executed")
            return

        # Search JSON query
        search = [
            [
                {
                    "link": "",
                    "field": "name",
                    "route": "asset/bases",
                    "value": "PC",
                    "object": "InventoryBase",
                    "operator": "icontains",
                    "fieldtype": "string",
                }
            ]
        ]

        # Sending the POST request with the authentication token
        response = self.client.post(
            "/search/",
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type": "application/json",
            },
            data=json.dumps({"search_data": search}),
        )

        if response.status_code in (200, 201):
            self.assets = response.json()
            asset_count = (
                len(self.assets)
                if isinstance(self.assets, list)
                else self.assets.get("count", "Assets not available")
            )
            print(
                f"Number of retrieved assets with the simple base search : {asset_count}"
            )
        else:
            print(
                "An error occured when attempt to execute the simple base search query : ",
                response.text,
            )

    @task
    def complexe_base_request(self):
        if not self.token:
            print("Token not available, request not executed")
            return

        search = [
            [
                {
                    "link": "",
                    "field": "name",
                    "route": "asset/bases",
                    "value": "PC",
                    "object": "InventoryBase",
                    "operator": "icontains",
                    "fieldtype": "string",
                },
                {
                    "object": "InventoryBase",
                    "route": "asset/bases",
                    "field": "osname",
                    "fieldtype": "string",
                    "operator": "istartswith",
                    "value": "Windows",
                    "link": "AND",
                },
            ]
        ]

        # Sending the POST request with the authentication token
        response = self.client.post(
            "/search/",
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type": "application/json",
            },
            data=json.dumps({"search_data": search}),
        )

        if response.status_code in (200, 201):
            self.assets = response.json()
            asset_count = (
                len(self.assets)
                if isinstance(self.assets, list)
                else self.assets.get("count", "Assets not available")
            )
            print(
                f"Number of retrieved assets with the complexe base search : {asset_count}"
            )
        else:
            print(
                "An error occured when attempt to execute the complexe base search query : ",
                response.text,
            )

    @task
    def simple_collection_request(self):
        if not self.token:
            print("Token not available, request not executed")
            return

        # Search JSON query
        search = [
            [
                {
                    "link": "",
                    "field": 264,
                    "route": "templates",
                    "value": "popos",
                    "object": "inventory_sections",
                    "section": 45,
                    "operator": "iexact",
                    "template": 2,
                    "fieldtype": "string",
                }
            ]
        ]

        # Sending the POST request with the authentication token
        response = self.client.post(
            "/search/",
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type": "application/json",
            },
            data=json.dumps({"search_data": search}),
        )

        if response.status_code in (200, 201):
            self.assets = response.json()
            asset_count = (
                len(self.assets)
                if isinstance(self.assets, list)
                else self.assets.get("count", "Assets not available")
            )
            print(
                f"Number of retrieved assets with the simple collection search : {asset_count}"
            )
        else:
            print(
                "An error occured when attempt to execute the simple collection search query : ",
                response.text,
            )
