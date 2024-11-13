import json

class Auth:
    @staticmethod
    def get_token(self):
        """
        Retrieve token auth
        """
        # User authentication
        response = self.client.post(
            "/api-auth/token",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"username": "admin", "password": "admin"})
        )
        # Check token retrieval
        if response.status_code == 200:
            return response.json().get("token")
        else:
            print("Login failed : ", response.text)