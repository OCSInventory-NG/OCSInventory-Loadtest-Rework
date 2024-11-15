from locust import HttpUser, task, between
from common.auth import Auth
import json
import random

class AssetBaseAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    assets = None
    os_options = ["windows", "linux", "mac"]

    def on_start(self):
        # Retrieve auth token at startup
        self.token = Auth.get_token(self)

    @task(3)
    def post_asset(self):
        """
        POST /asset/bases
        """
        if self.token:
            # Generate random num between 0001 and 9999
            random_number = f"{random.randint(1, 99999):05}"
            # Random selection of an operating system for osname
            osname = random.choice(self.os_options)

            # Data preparation with dynamic incrementation
            data = {
                "name": f"PC-{random_number}",
                "description": "Dummy Computer System Product for API test",
                "serial": f"00000-00000-00000-{random_number}",
                "osname": osname,
                "osversion": "1.0.0",
                "uuid": f"DUMMY-UUID{random_number}",
                "srcip": "127.0.0.1",
                "srcmac": "XX-XX-XX-XX-XX-XX",
                "domain": "WORKGROUP",
                "template": None
            }

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/asset/bases/",
                headers={"Authorization": f"Token {self.token}", "Content-Type": "application/json"},
                data=json.dumps(data)
            )
            
            if response.status_code != 200:
                print("An error occured when attempt to POST asset base : ", response.text)

        else:
            print("Token not available, request not executed")
            
    @task(2)
    def get_asset(self):
        """
        GET /asset/bases
        """
        if self.token:
            response = self.client.get(
                "/asset/bases/",
                headers={"Authorization": f"Token {self.token}"}
            )
            
            if response.status_code == 200:
                self.assets = response.json()
                asset_count = len(self.assets) if isinstance(self.assets, list) else self.assets.get("count", "Assets not available")
                print(f"Number of retrieved assets : {asset_count}")
            else:
                print("An error occured when attempt to retrieve asset base : ", response.text)
        else:
            print("Token not available, request not executed")
        
    @task
    def patch_asset(self):
        """
        PATCH /asset/bases/{id}
        """
        if not self.assets:
            print("No assets available for update")
            return
        
        if not self.token:
            print("Token not available, request not executed")
            return

        random_assets = random.sample(self.assets, min(10, len(self.assets)))
        asset_ids = [asset["id"] for asset in random_assets]
        
        update_data = {
            "description": "Updated by API test"
        }

        for asset_id in asset_ids:
            response = self.client.patch(
                f"/asset/bases/{asset_id}/",
                headers={"Authorization": f"Token {self.token}", "Content-Type": "application/json"},
                data=json.dumps(update_data)
            )
            
            if response.status_code != 200:
                print(f"An error occured when attempt to patch {asset_id} : {response.text}")

        