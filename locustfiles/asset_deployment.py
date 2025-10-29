from locust import HttpUser, task, between
from common.auth import Auth
import json
import random


class AssetDeploymentAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    os_options = ["WIN", "LIN", "MAC"]
    osname = None
    package_id = None
    package_name = None
    groups = []
    assets = []

    def on_start(self):
        # Retrieve auth token at startup
        self.token = Auth.get_token(self)

    def get_package_id(self):
        """
        GET /deployment/packages
        """
        if self.token:
            # Sending the GET request with the authentication token
            response = self.client.get(
                f"/deployment/packages/?name={self.package_name}",
                headers={
                    "Authorization": f"Token {self.token}",
                },
            )

            if response.status_code in (200, 201):
                self.package_id = response.json()[0].get("id")
            else:
                print(
                    "An error occured when attempt to POST deployment result : ",
                    response.text,
                )

        else:
            print("Token not available, request not executed")

    def get_assets(self):
        """
        GET /search
        """
        self.assets = []
        if self.token:
            search = [
                [
                    {
                        "object": "InventoryBase",
                        "route": "asset/bases",
                        "field": "osname",
                        "fieldtype": "string",
                        "operator": "icontains",
                        "value": self.osname,
                        "link": "AND",
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
                data=json.dumps(search),
            )

            if response.status_code in (200, 201):
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

    def get_group_by_os(self):
        """
        GET /asset/groups
        """
        self.groups = []
        if self.token:
            # Sending the GET request with the authentication token
            response = self.client.get(
                f"/asset/groups/?name={self.osname}",
                headers={
                    "Authorization": f"Token {self.token}",
                },
            )

            if response.status_code in (200, 201):
                # For single group
                # self.groups.append(response.json()[0].get("id"))

                # For multiple groups
                groups = response.json()
                for group in groups:
                    self.groups.append(group.get("id"))
            else:
                print(
                    "An error occured when attempt to POST deployment result : ",
                    response.text,
                )

        else:
            print("Token not available, request not executed")

    def create_asset_result(self):
        """
        POST /deployment/results
        """
        if self.token:
            # Generate random num between 00001 and 99999
            random_number = f"{random.randint(1, 99999):05}"

            self.get_package_id()
            self.get_assets()

            # Data preparation with dynamic incrementation
            for asset in self.assets:
                data = {
                    "package": self.package_id,
                    "asset": asset,
                    "group": None,
                    "name": f"Asset package {random_number}",
                    "status": 1,
                    "comment": "In waiting",
                }
                # Sending the POST request with the authentication token
                response = self.client.post(
                    "/deployment/results/",
                    headers={
                        "Authorization": f"Token {self.token}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(data),
                )

                if response.status_code not in (200, 201):
                    print(
                        "An error occured when attempt to POST asset deployment result : ",
                        response.text,
                    )

        else:
            print("Token not available, request not executed")

    def create_group_result(self):
        """
        POST /deployment/results
        """
        if self.token:
            # Generate random num between 00001 and 99999
            random_number = f"{random.randint(1, 99999):05}"

            self.get_package_id()
            self.get_group_by_os()

            # Data preparation with dynamic incrementation
            for group in self.groups:
                data = {
                    "package": self.package_id,
                    "asset": None,
                    "group": group,
                    "name": f"Group package {random_number}",
                    "status": 0,
                    "comment": "In waiting",
                }
                # Sending the POST request with the authentication token
                response = self.client.post(
                    "/deployment/results/",
                    headers={
                        "Authorization": f"Token {self.token}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(data),
                )

                if response.status_code not in (200, 201):
                    print(
                        "An error occured when attempt to POST group deployment result : ",
                        response.text,
                    )

        else:
            print("Token not available, request not executed")

    @task
    def create_package_for_asset(self):
        """
        POST /deployment/packages
        """
        if self.token:
            # Generate random num between 00001 and 99999
            random_number = f"{random.randint(1, 99999):05}"
            # Random selection of an operating system for osname
            self.osname = random.choice(self.os_options)

            # Data preparation with dynamic incrementation
            data = {
                "name": f"Dummy Asset Package {random_number}",
                "description": "Dummy Package for API test",
                "target_os": self.osname,
                "actions_list": [],
                "result": []
            }
            
            self.package_name = f"Dummy Asset Package {random_number}"

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/deployment/packages/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(data),
            )

            if response.status_code in (200, 201):
                self.create_asset_result()
            else:
                print(
                    "An error occured when attempt to POST deployment package : ",
                    response.text,
                )

        else:
            print("Token not available, request not executed")

    @task
    def create_package_for_group(self):
        """
        POST /deployment/packages
        """
        if self.token:
            # Generate random num between 00001 and 99999
            random_number = f"{random.randint(1, 99999):05}"
            # Random selection of an operating system for osname
            self.osname = random.choice(self.os_options)

            # Data preparation with dynamic incrementation
            data = {
                "name": f"Dummy Group Package {random_number}",
                "description": "Dummy Package for API test",
                "target_os": self.osname,
                "actions_list": [],
                "result": []
            }

            self.package_name = f"Dummy Group Package {random_number}"

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/deployment/packages/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(data),
            )
            
            if response.status_code in (200, 201):
                self.create_group_result()
            else:
                print(
                    "An error occured when attempt to POST deployment package : ",
                    response.text,
                )

        else:
            print("Token not available, request not executed")
