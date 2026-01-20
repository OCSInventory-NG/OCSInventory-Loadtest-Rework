from locust import HttpUser, task, between
from common.auth import Auth
import json
import random
import uuid


class AssetBaseAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    assets = None
    os_options = {
        "windows": [
            {"name": "Windows 10 Pro", "version": "10.0.19045.3930", "build": "22H2"},
            {
                "name": "Windows 11 Enterprise",
                "version": "11.0.22621.2715",
                "build": "22H2",
            },
            {
                "name": "Windows Server 2022",
                "version": "10.0.20348.2227",
                "build": "21H2",
            },
            {
                "name": "Windows 10 Education",
                "version": "10.0.19044.3448",
                "build": "21H2",
            },
            {"name": "Windows 11 Pro", "version": "11.0.22621.3235", "build": "23H2"},
            {
                "name": "Windows Server 2019",
                "version": "10.0.17763.253",
                "build": "1809",
            },
            {
                "name": "Windows Server 2016",
                "version": "10.0.14393.4583",
                "build": "1607",
            },
        ],
        "debian": [
            {
                "name": "Ubuntu 22.04 LTS",
                "version": "22.04.3",
                "distribution": "Jammy Jellyfish",
            },
            {
                "name": "Ubuntu 20.04 LTS",
                "version": "20.04.4",
                "distribution": "Focal Fossa",
            },
            {"name": "Debian 12", "version": "12.4", "distribution": "Bookworm"},
            {"name": "Debian 11", "version": "11.2", "distribution": "Bullseye"},
        ],
        "rhel": [
            {
                "name": "Red Hat Enterprise Linux 9.3",
                "version": "9.3",
                "distribution": "Plow",
            },
            {"name": "CentOS Stream 9", "version": "9", "distribution": "Stream"},
            {"name": "CentOS 8", "version": "8.5", "distribution": "CentOS"},
            {"name": "Fedora 39", "version": "39", "distribution": "Thirty Nine"},
            {"name": "Fedora 38", "version": "38", "distribution": "Thirty Eight"},
            {"name": "Fedora 37", "version": "37", "distribution": "Thirty Seven"},
            {
                "name": "Rocky Linux 8.5",
                "version": "8.5",
                "distribution": "Green Obsidian",
            },
        ],
        "mac": [
            {"name": "macOS Monterey", "version": "12.3", "build": "21E230"},
            {"name": "macOS Big Sur", "version": "11.6.4", "build": "20G230"},
            {"name": "macOS Catalina", "version": "10.15.7", "build": "19H15"},
            {"name": "macOS Mojave", "version": "10.14.6", "build": "18G103"},
            {"name": "macOS High Sierra", "version": "10.13.6", "build": "17G14019"},
        ],
    }

    def generate_serial_number(self, os_type):
        """Generate a realistic serial number based on OS type"""
        prefixes = {
            "windows": ["00331", "00426", "00512"],
            "debian": ["LNX", "SRV", "DEB"],
            "rhel": ["LNX", "SRV", "RHEL"],
            "mac": ["C02", "D25", "K02"],
        }
        prefix = random.choice(prefixes[os_type])
        return f"{prefix}-{random.randint(10000, 99999)}-{random.randint(10000, 99999)}"

    def generate_mac_address(self):
        """Generate a realistic MAC address"""
        return ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])

    def on_start(self):
        """
        Retrieve auth token at startup
        """
        self.token = Auth.get_token(self)

    @task
    def post_asset(self):
        """
        POST /asset/bases
        """
        if self.token:
            # Generate random num between 00001 and 99999
            random_number = f"{random.randint(1, 99999):05}"
            # Random selection of an operating system for osname
            os_type = random.choice(list(self.os_options.keys()))
            os_details = random.choice(self.os_options[os_type])
            unique_uuid = str(uuid.uuid4())
            template_map = {"windows": 5, "debian": 2, "rhel": 3, "mac": 4}
            template = template_map[os_type]

            # Data preparation with dynamic incrementation
            data = {
                "name": f"PC-{os_details['name'].upper()}-{random_number}",
                "description": "System not updated",
                "serial": f"00000-00000-00000-{random_number}",
                "osname": os_details["name"],
                "osversion": os_details["version"],
                "uuid": unique_uuid,
                "srcip": f"192.168.{random.randint(0, 255)}.{random.randint(1, 254)}",
                "srcmac": self.generate_mac_address(),
                "domain": (
                    random.choice(["WORKGROUP", "ENTERPRISE", "LOCAL"])
                    if os_type == "windows"
                    else random.choice(["WORKGROUP", "CORP", "LOCAL"])
                ),
                "template": template,
            }

            # Sending the POST request with the authentication token
            response = self.client.post(
                "/asset/bases/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(data),
            )

            if response.status_code not in (200, 201):
                print(
                    "An error occured when attempt to POST asset base : ", response.text
                )

        else:
            print("Token not available, request not executed")

    @task
    def get_asset(self):
        """
        GET /asset/bases/
        """
        if self.token:
            response = self.client.get(
                "/asset/bases/", headers={"Authorization": f"Token {self.token}"}
            )

            if response.status_code in (200, 201):
                self.assets = response.json()
                asset_count = (
                    len(self.assets)
                    if isinstance(self.assets, list)
                    else self.assets.get("count", "Assets not available")
                )
                print(f"Number of retrieved assets : {asset_count}")
            else:
                print(
                    "An error occured when attempt to retrieve asset base : ",
                    response.text,
                )
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

        update_data = {"description": "System updated"}

        for asset_id in asset_ids:
            response = self.client.patch(
                f"/asset/bases/{asset_id}/",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(update_data),
            )

            if response.status_code != 200:
                print(
                    f"An error occured when attempt to patch {asset_id} : {response.text}"
                )
