from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.parse, urllib.error

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"

# EMEA countries to search across when location is EMEA
EMEA_COUNTRIES = ["gb", "de", "fr", "nl", "ae", "za", "sg"]


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs     = urllib.parse.parse_qs(parsed.query)

            title    = qs.get("title",    [""])[0].strip()
            location = qs.get("location", [""])[0].strip()
            limit    = int(qs.get("limit", ["10"])[0])

            if not title:
                self._json({"error": "title parameter required"}, 400)
                return

            app_id  = os.environ.get("ADZUNA_APP_ID", "")
            app_key = os.environ.get("ADZUNA_APP_KEY", "")
            if not app_id or not app_key:
                self._json({"error": "ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables not set"}, 500)
                return

            loc_lower = location.lower()
            if not location or "emea" in loc_lower or "worldwide" in loc_lower or "global" in loc_lower:
                countries = EMEA_COUNTRIES
            elif "uk" in loc_lower or "united kingdom" in loc_lower or "britain" in loc_lower:
                countries = ["gb"]
            elif "uae" in loc_lower or "dubai" in loc_lower or "emirates" in loc_lower:
                countries = ["ae"]
            elif "germany" in loc_lower or "deutschland" in loc_lower:
                countries = ["de"]
            elif "france" in loc_lower or "paris" in loc_lower:
                countries = ["fr"]
            elif "netherlands" in loc_lower or "amsterdam" in loc_lower:
                countries = ["nl"]
            else:
                countries = EMEA_COUNTRIES

            jobs = []
            seen = set()

            for country in countries:
                if len(jobs) >= limit:
                    break

                params = urllib.parse.urlencode({
                    "app_id":         app_id,
                    "app_key":        app_key,
                    "results_per_page": min(limit, 10),
                    "what":           title,
                    "where":          location if location and "emea" not in loc_lower else "",
                    "content-type":   "application/json",
                    "sort_by":        "date",
                })
                url = f"{ADZUNA_BASE}/{country}/search/1?{params}"

                req = urllib.request.Request(url, method="GET")

                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read())
                except urllib.error.HTTPError as e:
                    continue  # skip countries that error

                for item in data.get("results", []):
                    job_id = str(item.get("id", ""))
                    if job_id in seen:
                        continue
                    seen.add(job_id)

                    loc_parts = []
                    if item.get("location", {}).get("display_name"):
                        loc_parts.append(item["location"]["display_name"])

                    jobs.append({
                        "id":          job_id,
                        "title":       item.get("title", ""),
                        "company":     item.get("company", {}).get("display_name", ""),
                        "location":    loc_parts[0] if loc_parts else country.upper(),
                        "description": item.get("description", ""),
                        "url":         item.get("redirect_url", ""),
                        "posted":      item.get("created", "")[:10] if item.get("created") else "",
                        "salary":      item.get("salary_is_predicted") and f"{item.get('salary_min','')}–{item.get('salary_max','')} {item.get('salary_currency','')}" or "",
                    })

                    if len(jobs) >= limit:
                        break

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
