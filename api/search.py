from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.parse, urllib.error

RAPIDAPI_HOST = "jsearch.p.rapidapi.com"
RAPIDAPI_URL  = f"https://{RAPIDAPI_HOST}/search"


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs     = urllib.parse.parse_qs(parsed.query)

            title    = qs.get("title",    [""])[0].strip()
            location = qs.get("location", [""])[0].strip()

            if not title:
                self._json({"error": "title parameter required"}, 400)
                return

            api_key = os.environ.get("RAPIDAPI_KEY", "")
            if not api_key:
                self._json({"error": "RAPIDAPI_KEY environment variable not set"}, 500)
                return

            query = f"{title} in {location}" if location else title

            params = urllib.parse.urlencode({
                "query":        query,
                "num_pages":    "1",
                "date_posted":  "month",
            })
            url = f"{RAPIDAPI_URL}?{params}"

            req = urllib.request.Request(
                url,
                headers={
                    "x-rapidapi-host": RAPIDAPI_HOST,
                    "x-rapidapi-key":  api_key,
                },
                method="GET"
            )

            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = json.loads(resp.read())
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                self._json({"error": f"API {e.code}: {body[:300]}"}, 502)
                return

            jobs = []
            for item in raw.get("data", []):
                jobs.append({
                    "id":          item.get("job_id", ""),
                    "title":       item.get("job_title", ""),
                    "company":     item.get("employer_name", ""),
                    "location":    f"{item.get('job_city', '')} {item.get('job_country', '')}".strip(),
                    "description": item.get("job_description", ""),
                    "url":         item.get("job_apply_link", item.get("job_google_link", "")),
                    "posted":      item.get("job_posted_at_datetime_utc", "")[:10] if item.get("job_posted_at_datetime_utc") else "",
                })

            self._json({"jobs": jobs, "count": len(jobs)})

        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if self.command == "OPTIONS":
            self.send_response(200)
            self.end_headers()
