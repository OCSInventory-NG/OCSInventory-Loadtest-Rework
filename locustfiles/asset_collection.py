from locust import HttpUser, task, between
from common.auth import Auth
import json
import random

class AssetCollectionAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    assets = None
    os_options = ["windows", "linux"]

    def on_start(self):
        # Retrieve auth token at startup
        self.token = Auth.get_token(self)
    
    def load_template_inventory(self, file_path):
        """
        Load JSON template inventory file.
        """
        try:
            with open(file_path, "r") as file:
                data = json.load(file)
                return data.get("template_inventory", None)
        except Exception as e:
            print(f"An error occured whend attemps to load json inventory file : {e}")
            return None
        
    @task
    def post_inventory(self):
        """
        POST /asset/collection
        """
        if self.token:
            # Generate random num between 0001 and 9999
            random_number = f"{random.randint(1, 99999):05}"
            # Random selection of an operating system for osname
            osname = random.choice(self.os_options)
            
            if osname == "windows":
                template = 4
            elif osname == "linux":
                template = 2
            else:
                template = 3
                
            file_path = "files/{osname}_inventory.json".format(osname=osname)
            template_inventory = self.load_template_inventory(file_path)
            
            if not template_inventory:
                print("Unable to load 'template_inventory' from JSON file")
                return

            # Data preparation with dynamic incrementation
            data = {
                "name": f"PC-COMPLETE-{random_number}",
                "description": "Dummy Computer System Product for API test",
                "serial": f"00000-00000-00000-{random_number}",
                "osname": osname,
                "osversion": "1.0.0",
                "uuid": f"DUMMY-UUID-COMPLETE-{random_number}",
                "srcip": "127.0.0.1",
                "srcmac": "XX-XX-XX-XX-XX-XX",
                "domain": "WORKGROUP",
                "template": template,
                "template_inventory": template_inventory
            }

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/asset/collection/",
                headers={"Authorization": f"Token {self.token}", "Content-Type": "application/json"},
                data=json.dumps(data)
            )
            
            if response.status_code != 201:
                print("An error occured when attempt to POST asset collection : ", response.text)

        else:
            print("Token not available, request not executed")
            
    @task
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