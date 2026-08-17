from locust import HttpUser, task, between
from common.auth import Auth
import json
import random

# Realistic enterprise deployment catalog (software installs, patches,
# scripts, configuration files), grouped by target OS, so generated
# packages read like an actual IT deployment flow instead of
# "Dummy Package NNNNN".
#
# Each package carries the ordered list of deployment actions a real
# admin would attach to it - most are a single step, but a few are a
# realistic 2-step flow (drop a file, then apply/use it), covering the 3
# action types the agent understands (see
# OCSInventory-Agent-Rework/lib/core/deployment.dart::executeActions):
#   - EXEC  : run a shell/PowerShell command as-is, no file involved.
#   - STORE : download "file" and drop it at the "command" path (used as
#             a destination directory), no execution.
#   - LAUNCH: download "file" and execute it via "command". $PACKAGE is
#             the agent's per-package download directory (see
#             Deployment.executeCommand's variable substitution).
# "file" is (filename, content) for STORE/LAUNCH; omitted for EXEC.
# Priority (execution order) is implicit in list position.
# Result status : most deployments of a real fleet end up successful,
# a chunk is still mid-flight (waiting for the agent to notify/pick it
# up), and only a minority actually errors out - see
# deployment/result/models.py::Result.STATUS_CHOICES for the meaning of
# each code.
RESULT_STATUSES = ["0", "1", "2", "3"]
RESULT_STATUS_WEIGHTS = [6, 2, 1, 1]
RESULT_STATUS_COMMENTS = {
    "0": "Deploiement termine avec succes.",
    "1": "En attente de notification par l'agent.",
    "2": "Paquet notifie a l'agent, execution en cours.",
    "3": "Echec du deploiement - voir les journaux de l'agent.",
}


def _random_result_status():
    return random.choices(RESULT_STATUSES, weights=RESULT_STATUS_WEIGHTS, k=1)[0]


DEPLOYMENT_PACKAGES = {
    "WIN": [
        {
            "name": "Deploiement - 7-Zip 23.01",
            "description": "Installation de l'utilitaire d'archivage 7-Zip",
            "actions": [
                {
                    "name": "Installation silencieuse de 7-Zip",
                    "type": "LAUNCH",
                    "command": "$PACKAGE/7z2301-x64.exe /S",
                    "file": ("7z2301-x64.exe", b"REM stub installer - 7-Zip 23.01 x64 silent setup\n"),
                },
                {
                    "name": "Nettoyage du programme d'installation",
                    "type": "EXEC",
                    "command": "del /q $PACKAGE\\7z2301-x64.exe",
                },
            ],
        },
        {
            "name": "Deploiement - Google Chrome Enterprise",
            "description": "Installation du navigateur Google Chrome (MSI Enterprise)",
            "actions": [
                {
                    "name": "Installation silencieuse de Chrome Enterprise",
                    "type": "LAUNCH",
                    "command": "msiexec /i $PACKAGE/GoogleChromeEnterpriseBundle.msi /quiet /norestart",
                    "file": ("GoogleChromeEnterpriseBundle.msi", b"stub MSI - Google Chrome Enterprise Bundle\n"),
                },
                {
                    "name": "Application de la politique navigateur par defaut",
                    "type": "EXEC",
                    "command": 'reg add "HKLM\\Software\\Policies\\Google\\Chrome" /v DefaultBrowserSettingEnabled /t REG_DWORD /d 1 /f',
                },
            ],
        },
        {
            "name": "Deploiement - Microsoft Office 365",
            "description": "Installation de la suite bureautique Microsoft Office 365",
            "actions": [
                {
                    "name": "Deploiement d'Office 365 via ODT",
                    "type": "LAUNCH",
                    "command": "$PACKAGE/setup.exe /configure $PACKAGE/configuration.xml",
                    "file": ("setup.exe", b"stub - Office Deployment Tool\n"),
                },
            ],
        },
        {
            "name": "Mise a jour - Adobe Acrobat Reader DC",
            "description": "Mise a jour de securite d'Adobe Acrobat Reader DC",
            "actions": [
                {
                    "name": "Mise a jour silencieuse d'Acrobat Reader DC",
                    "type": "LAUNCH",
                    "command": "$PACKAGE/AcroRdrDCUpd.exe /sAll /rs /msi EULA_ACCEPT=YES",
                    "file": ("AcroRdrDCUpd.exe", b"stub - Adobe Acrobat Reader DC updater\n"),
                },
            ],
        },
        {
            "name": "Patch - Windows Security Update KB5034441",
            "description": "Application du correctif de securite Windows KB5034441",
            "actions": [
                {
                    "name": "Application du correctif KB5034441",
                    "type": "EXEC",
                    "command": "wusa.exe C:\\Windows\\Temp\\KB5034441.msu /quiet /norestart",
                },
            ],
        },
        {
            "name": "Script - Nettoyage disque C:",
            "description": "Execution du script de nettoyage de l'espace disque",
            "actions": [
                {
                    "name": "Nettoyage automatique du disque C:",
                    "type": "EXEC",
                    "command": "cleanmgr.exe /sagerun:1",
                },
            ],
        },
        {
            "name": "Configuration - Proxy entreprise v2",
            "description": "Deploiement du fichier de configuration du proxy du parc bureautique",
            "actions": [
                {
                    "name": "Depot du fichier de configuration proxy",
                    "type": "STORE",
                    "command": "C:\\ProgramData\\Entreprise\\Proxy",
                    "file": (
                        "proxy.pac",
                        b'function FindProxyForURL(url, host) { return "PROXY proxy.entreprise.local:8080; DIRECT"; }\n',
                    ),
                },
                {
                    "name": "Application du proxy au niveau systeme",
                    "type": "EXEC",
                    "command": 'netsh winhttp set proxy proxy.entreprise.local:8080',
                },
            ],
        },
    ],
    "LIN": [
        {
            "name": "Deploiement - OpenJDK 25",
            "description": "Installation du runtime Java OpenJDK 25",
            "actions": [
                {
                    "name": "Installation d'OpenJDK 25 via APT",
                    "type": "EXEC",
                    "command": "apt-get install -y openjdk-25-jre-headless",
                },
            ],
        },
        {
            "name": "Deploiement - Docker Engine",
            "description": "Installation du moteur de conteneurisation Docker",
            "actions": [
                {
                    "name": "Installation du moteur Docker",
                    "type": "EXEC",
                    "command": "curl -fsSL https://get.docker.com | sh",
                },
                {
                    "name": "Activation et demarrage du service Docker",
                    "type": "EXEC",
                    "command": "systemctl enable --now docker",
                },
            ],
        },
        {
            "name": "Mise a jour - Paquets de securite (APT)",
            "description": "Application des mises a jour de securite via apt-get",
            "actions": [
                {
                    "name": "Mise a jour des paquets systeme",
                    "type": "EXEC",
                    "command": "apt-get update && apt-get -y upgrade",
                },
            ],
        },
        {
            "name": "Script - Purge des journaux applicatifs",
            "description": "Execution du script de purge des logs applicatifs",
            "actions": [
                {
                    "name": "Purge des journaux applicatifs",
                    "type": "EXEC",
                    "command": "find /var/log -name '*.log' -mtime +30 -delete",
                },
            ],
        },
        {
            "name": "Configuration - Agent de supervision Zabbix",
            "description": "Deploiement du fichier de configuration de l'agent de supervision",
            "actions": [
                {
                    "name": "Depot du fichier de configuration Zabbix",
                    "type": "STORE",
                    "command": "/etc/zabbix",
                    "file": (
                        "zabbix_agentd.conf",
                        b"Server=zabbix.entreprise.local\nServerActive=zabbix.entreprise.local\nHostname=Agent\n",
                    ),
                },
                {
                    "name": "Redemarrage de l'agent Zabbix",
                    "type": "EXEC",
                    "command": "systemctl restart zabbix-agent",
                },
            ],
        },
    ],
    "MAC": [
        {
            "name": "Deploiement - Google Chrome",
            "description": "Installation du navigateur Google Chrome",
            "actions": [
                {
                    "name": "Installation de Google Chrome",
                    "type": "LAUNCH",
                    "command": "installer -pkg $PACKAGE/googlechrome.pkg -target /",
                    "file": ("googlechrome.pkg", b"stub - Google Chrome installer package\n"),
                },
            ],
        },
        {
            "name": "Mise a jour - macOS Security Update",
            "description": "Application de la mise a jour de securite macOS",
            "actions": [
                {
                    "name": "Application de la mise a jour de securite macOS",
                    "type": "EXEC",
                    "command": "softwareupdate -ia --agree-to-license",
                },
            ],
        },
        {
            "name": "Configuration - Profil VPN entreprise",
            "description": "Deploiement du profil de configuration VPN",
            "actions": [
                {
                    "name": "Depot du profil de configuration VPN",
                    "type": "STORE",
                    "command": "/Library/Managed Preferences",
                    "file": (
                        "vpn-entreprise.mobileconfig",
                        b'<?xml version="1.0" encoding="UTF-8"?>\n<!-- stub VPN configuration profile -->\n',
                    ),
                },
                {
                    "name": "Installation du profil VPN",
                    "type": "EXEC",
                    "command": "profiles install -type configuration -path /Library/Managed Preferences/vpn-entreprise.mobileconfig",
                },
            ],
        },
        {
            "name": "Script - Nettoyage du cache utilisateur",
            "description": "Execution du script de nettoyage du cache utilisateur",
            "actions": [
                {
                    "name": "Nettoyage du cache utilisateur",
                    "type": "EXEC",
                    "command": "rm -rf ~/Library/Caches/*",
                },
            ],
        },
    ],
}


class AssetDeploymentAPITest(HttpUser):
    wait_time = between(1, 5)
    token = None
    os_options = ["WIN", "LIN", "MAC"]
    osname = None
    link_osname_osopt = {
        "WIN": ["Windows"],
        "LIN": ["Ubuntu", "Debian", "CentOS", "Fedora"],
        "MAC": ["macOS"]
    }
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
                        "operator": "istartswith",
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
                data=json.dumps({"search_data": search}),
            )

            if response.status_code in (200, 201):
                assets = response.json()
                for asset in assets:
                    self.assets.append(asset.get("id"))
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
            name = f"Dummy {self.osname} group"
            # Sending the GET request with the authentication token
            response = self.client.get(
                f"/asset/groups/?name={name}",
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

    def create_package_actions(self, package_id, action_defs):
        """
        POST /deployment/actions/ once per action, in order.

        Attaches the ordered action(s) from DEPLOYMENT_PACKAGES to the
        package just created, so it shows up as a real deployment
        (EXEC/STORE/LAUNCH, sometimes a 2-step store-then-apply flow)
        instead of an empty package. EXEC needs no file, so it's posted
        as plain JSON; STORE/LAUNCH need a file, so they're posted as
        multipart/form-data (the "uploaded_file" field the backend's
        FileUploadMixin expects). "priority" reflects list order here,
        but is recomputed server-side regardless (see
        ActionSerializer.create), so it's mostly documentation.
        """
        if not package_id:
            return

        for priority, action_def in enumerate(action_defs, start=1):
            fields = {
                "package": package_id,
                "name": action_def["name"],
                "priority": priority,
                "action_type": action_def["type"],
                "command": action_def["command"],
            }

            if action_def["type"] == "EXEC":
                response = self.client.post(
                    "/deployment/actions/",
                    headers={
                        "Authorization": f"Token {self.token}",
                        "Content-Type": "application/json",
                    },
                    data=json.dumps(fields),
                )
            else:
                file_name, file_content = action_def["file"]
                response = self.client.post(
                    "/deployment/actions/",
                    headers={"Authorization": f"Token {self.token}"},
                    data=fields,
                    files={"uploaded_file": (file_name, file_content, "application/octet-stream")},
                )

            if response.status_code not in (200, 201):
                print(
                    "An error occured when attempt to POST deployment action : ",
                    response.text,
                )

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
                random_status = _random_result_status()
                data = {
                    "package": self.package_id,
                    "asset": asset,
                    "group": None,
                    "name": f"Asset package {random_number}",
                    "status": random_status,
                    "comment": RESULT_STATUS_COMMENTS[random_status],
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
            self.get_assets()

            if not self.groups:
                print("create_group_result: no groups found, cannot assign machines")
                return

            if not self.assets:
                print("create_group_result: no assets found for osname", self.osname)
                return

            # Data preparation with dynamic incrementation
            for group in self.groups:
                for asset in self.assets:
                    random_status = _random_result_status()
                    data = {
                        "package": self.package_id,
                        "asset": asset,
                        "group": group,
                        "name": f"Group package {random_number}",
                        "status": random_status,
                        "comment": RESULT_STATUS_COMMENTS[random_status],
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
            ostarget = random.choice(self.os_options)
            self.osname = random.choice(self.link_osname_osopt[ostarget])
            package_def = random.choice(DEPLOYMENT_PACKAGES[ostarget])
            package_name = f"{package_def['name']} ({random_number})"

            # Data preparation with dynamic incrementation
            data = {
                "name": package_name,
                "description": package_def["description"],
                "target_os": ostarget,
                "actions_list": [],
                "result": []
            }

            self.package_name = package_name

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
                self.create_package_actions(response.json().get("id"), package_def["actions"])
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
            ostarget = random.choice(self.os_options)
            self.osname = random.choice(self.link_osname_osopt[ostarget])
            package_def = random.choice(DEPLOYMENT_PACKAGES[ostarget])
            package_name = f"{package_def['name']} ({random_number})"

            # Data preparation with dynamic incrementation
            data = {
                "name": package_name,
                "description": package_def["description"],
                "target_os": ostarget,
                "actions_list": [],
                "result": []
            }

            self.package_name = package_name

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
                self.create_package_actions(response.json().get("id"), package_def["actions"])
                self.create_group_result()
            else:
                print(
                    "An error occured when attempt to POST deployment package : ",
                    response.text,
                )

        else:
            print("Token not available, request not executed")
