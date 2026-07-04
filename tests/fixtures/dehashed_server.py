import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        resp = {
            "balance": 100,
            "entries": [
                {
                    "id": "5603802198",
                    "email": ["test@example.com"],
                    "ip_address": ["127.0.0.1"],
                    "username": ["username@example.com"],
                    "password": ["examplepassword"],
                    "hashed_password": ["password:salt||passwordhash"],
                    "name": ["name"],
                    "dob": ["01/02/60"],
                    "license_plate": ["123456"],
                    "address": ["example address"],
                    "phone": ["+18005551234"],
                    "company": ["example company"],
                    "url": ["url.com"],
                    "social": ["social username"],
                    "cryptocurrency_address": ["0xcryptocurrencyaddress"],
                    "database_name": "Example Database Name",
                    "raw_record": {"le_only": True, "unstructured": True},
                }
            ],
            "took": "179µs",
            "total": 5,
        }

        self.wfile.write(json.dumps(resp).encode("utf-8"))


if __name__ == "__main__":
    # Port 8002 to avoid colliding with the Keen web server's default (8000).
    server = HTTPServer(("", 8002), Handler)
    server.serve_forever()
