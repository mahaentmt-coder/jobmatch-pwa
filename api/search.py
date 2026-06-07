from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.parse, urllib.error

RAPIDAPI_HOST = "linkedin-jobs-search.p.rapidapi.com"
RAPIDAPI_URL  = f"https://{RAPIDAPI_HOST}/"


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

            api_key = os.environ.get("RAPIDAPI_KEY", "")
            if not api_key:
                self._json({"error": "RAPIDAPI_KEY environment variable not set"}, 500)
                return

            # Build keyword query — handle OR syntax
            # "Digital Transformation Director or Executive" → keywords as-is
            keywords = title

            params = urllib.parse.urlencode({
                "keywords":        keywords,
                "location":        location or "Worldwide",
                "dateSincePosted": "past month",
                "jobType":         "full time",
                "limit":           str(min(limit, 10)),
                "offset":          "0",
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
                self._json({"error": f"LinkedIn API {e.code}: {body[:300]}"}, 502)
                return

            # Normalise response — returns a list directly
            items = raw if isinstance(raw, list) else raw.get("data", raw.get("jobs", []))

            jobs = []
            for item in items:
                title_str   = item.get("position", item.get("title", ""))
                title_lower = title_str.lower()
                company     = item.get("company",  item.get("companyName", ""))
                location_str = item.get("location", item.get("jobLocation", ""))
                url_str      = item.get("jobUrl",  item.get("url", item.get("applyUrl", "")))
                posted       = item.get("postedAt", item.get("date", item.get("publishedAt", "")))
                description  = item.get("description", item.get("jobDescription", ""))
                salary_str   = item.get("salary", item.get("salaryRange", ""))

                # Infer seniority from title
                if any(w in title_lower for w in ["chief", "cto", "cio", "cdo", "cxo", "vp", "vice president", "c-suite"]):
                    seniority = "Executive"
                elif any(w in title_lower for w in ["director", "head of", "principal"]):
                    seniority = "Director"
                elif any(w in title_lower for w in ["senior", "lead", "manager", "architect"]):
                    seniority = "Senior"
                elif any(w in title_lower for w in ["junior", "graduate", "intern", "entry"]):
                    seniority = "Junior"
                else:
                    seniority = "Mid"

                jobs.append({
                    "id":            item.get("id", item.get("jobId", str(len(jobs)))),
                    "title":         title_str,
                    "company":       company,
                    "location":      location_str,
                    "description":   description,
                    "url":           url_str,
                    "posted":        str(posted)[:10] if posted else "",
                    "salary":        str(salary_str) if salary_str else "",
                    "seniority":     seniority,
                    "contract_type": item.get("employmentType", item.get("jobType", "")),
                    "contract_time": "",
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
