from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

RAPIDAPI_HOST = "jsearch.p.rapidapi.com"
RAPIDAPI_URL  = f"https://{RAPIDAPI_HOST}/search"

EMEA_LOCATIONS = ["UK", "UAE", "Germany", "Netherlands"]


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

            loc_lower = location.lower()
            is_emea   = not location or any(k in loc_lower for k in ["emea", "worldwide", "global", "remote"])

            queries = []
            if is_emea:
                for country in EMEA_LOCATIONS:
                    queries.append(f"{title} in {country}")
            else:
                queries.append(f"{title} in {location}")

            def fetch_query(query):
                # Fetch 2 pages per query so after dedup we always hit the limit
                params = urllib.parse.urlencode({
                    "query":            query,
                    "page":             "1",
                    "num_pages":        "2",
                    "date_posted":      "month",
                    "employment_types": "FULLTIME",
                })
                req = urllib.request.Request(
                    f"{RAPIDAPI_URL}?{params}",
                    headers={
                        "x-rapidapi-host": RAPIDAPI_HOST,
                        "x-rapidapi-key":  api_key,
                    },
                    method="GET"
                )
                try:
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        return json.loads(resp.read()).get("data", [])
                except Exception:
                    return []

            # Fetch all queries in parallel
            all_items = []
            with ThreadPoolExecutor(max_workers=4) as pool:
                for result in as_completed([pool.submit(fetch_query, q) for q in queries]):
                    all_items.extend(result.result())

            jobs = []
            seen = set()

            for item in all_items:
                if len(jobs) >= limit:
                    break

                job_id = item.get("job_id", "")
                if job_id in seen:
                    continue
                seen.add(job_id)

                title_str   = item.get("job_title", "")
                title_lower = title_str.lower()

                # Infer seniority from title
                if any(w in title_lower for w in ["chief", "cto", "cio", "cdo", "vp", "vice president"]):
                    seniority = "Executive"
                elif any(w in title_lower for w in ["director", "head of", "principal"]):
                    seniority = "Director"
                elif any(w in title_lower for w in ["senior", "lead", "manager", "architect"]):
                    seniority = "Senior"
                elif any(w in title_lower for w in ["junior", "graduate", "intern", "entry"]):
                    seniority = "Junior"
                else:
                    seniority = "Mid"

                # Salary
                sal_min = item.get("job_min_salary")
                sal_max = item.get("job_max_salary")
                period  = item.get("job_salary_period", "")
                if sal_min and sal_max:
                    salary = f"{int(sal_min):,} – {int(sal_max):,}"
                    if period:
                        salary += f" / {period.lower()}"
                elif sal_min:
                    salary = f"{int(sal_min):,}+" + (f" / {period.lower()}" if period else "")
                else:
                    salary = ""

                city    = item.get("job_city", "") or ""
                country = item.get("job_country", "") or ""
                loc_str = ", ".join(filter(None, [city, country]))

                jobs.append({
                    "id":            job_id,
                    "title":         title_str,
                    "company":       item.get("employer_name", ""),
                    "logo":          item.get("employer_logo", ""),
                    "location":      loc_str,
                    "description":   item.get("job_description", ""),
                    "url":           item.get("job_apply_link", item.get("job_google_link", "")),
                    "posted":        item.get("job_posted_at", ""),
                    "salary":        salary,
                    "seniority":     seniority,
                    "contract_type": item.get("job_employment_type", ""),
                    "remote":        item.get("job_is_remote", False),
                    "benefits":      (item.get("job_benefits_strings") or [])[:3],
                    "publisher":     item.get("job_publisher", ""),
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
