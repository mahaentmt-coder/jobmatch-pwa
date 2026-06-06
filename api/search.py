from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.parse, urllib.error

RAPIDAPI_HOST = "linkedin-job-search-api.p.rapidapi.com"
RAPIDAPI_URL  = f"https://{RAPIDAPI_HOST}/active-jb-24h"


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs     = urllib.parse.parse_qs(parsed.query)

            title    = qs.get("title",    [""])[0].strip()
            location = qs.get("location", [""])[0].strip()
            limit    = qs.get("limit",    ["10"])[0]

            if not title:
                self._json({"error": "title parameter required"}, 400)
                return

            api_key = os.environ.get("RAPIDAPI_KEY", "")
            if not api_key:
                self._json({"error": "RAPIDAPI_KEY environment variable not set"}, 500)
                return

            # Build params — omit location_filter if blank to avoid API errors
            params_dict = {
                "limit":            limit,
                "offset":           "0",
                "title_filter":     f'"{title}"',
                "description_type": "text",
            }
            if location:
                params_dict["location_filter"] = f'"{location}"'

            url = f"{RAPIDAPI_URL}?{urllib.parse.urlencode(params_dict)}"

            req = urllib.request.Request(
                url,
                headers={
                    "Content-Type":    "application/json",
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
                self._json({"error": f"RapidAPI {e.code}: {body[:300]}"}, 502)
                return

            # Normalise — API returns a list directly
            items = raw if isinstance(raw, list) else raw.get("data", raw.get("jobs", []))

            jobs = []
            for item in items:
                company = item.get("company", "")
                if isinstance(company, dict):
                    company = company.get("name", "")

                location_val = item.get("location", "")
                if isinstance(location_val, dict):
                    location_val = location_val.get("city", location_val.get("country", ""))

                jobs.append({
                    "id":          str(item.get("id", item.get("job_id", ""))),
                    "title":       item.get("title", ""),
                    "company":     company,
                    "location":    location_val,
                    "description": item.get("description", item.get("job_description", "")),
                    "url":         item.get("url", item.get("job_url", item.get("linkedin_url", ""))),
                    "posted":      item.get("posted_at", item.get("date", item.get("created_at", ""))),
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
