import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()

        resp = {
            "data": {
                "id": "c60ef040-ce2c-56bc-9296-40ac52c18780",
                "name": {
                    "fullName": "Patrick Bosmans",
                    "givenName": "Patrick",
                    "familyName": "Bosmans",
                },
                "email": "patrick@stripe.com",
                "location": "Madison, Wisconsin, United States",
                "timeZone": "America/Chicago",
                "utcOffset": -6,
                "geo": {
                    "city": "Madison",
                    "state": "Wisconsin",
                    "stateCode": "WI",
                    "country": "United States",
                    "countryCode": "US",
                    "lat": 43.07305,
                    "lng": -89.40123,
                },
                "bio": None,
                "site": None,
                "avatar": None,
                "employment": {
                    "domain": "stripe.com",
                    "name": "Stripe",
                    "title": "IT Administrator",
                    "role": "it",
                    "subRole": None,
                    "seniority": "executive",
                },
                "facebook": {"handle": None},
                "github": {
                    "handle": None,
                    "id": None,
                    "avatar": None,
                    "company": None,
                    "blog": None,
                    "followers": None,
                    "following": None,
                },
                "twitter": {
                    "handle": None,
                    "id": None,
                    "bio": None,
                    "followers": None,
                    "following": None,
                    "statuses": None,
                    "favorites": None,
                    "location": None,
                    "site": None,
                    "avatar": None,
                },
                "linkedin": {"handle": "patrick-bosmans-549746b4"},
                "googleplus": {"handle": None},
                "gravatar": {"handle": None, "urls": [], "avatar": None, "avatars": []},
                "fuzzy": False,
                "emailProvider": "google.com",
                "indexedAt": "2026-05-11",
                "phone": "+1 307 512 2554",
                "activeAt": "2026-05-11",
                "inactiveAt": None,
            },
            "meta": {"email": "patrick@stripe.com"},
        }

        self.wfile.write(json.dumps(resp).encode("utf-8"))


if __name__ == "__main__":
    server = HTTPServer(("", 8001), Handler)
    server.serve_forever()
