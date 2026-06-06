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

            # Parse OR queries: "Digital Transformation Director or Executive"
            # → what_phrase="Digital Transformation", what_or="Director Executive"
            what_phrase = title
            what_or     = ""
            if " or " in title.lower():
                idx   = title.lower().index(" or ")
                left  = title[:idx].strip()   # "Digital Transformation Director"
                right = title[idx+4:].strip() # "Executive"
                left_words  = left.split()
                right_words = right.split()
                # Right side is the alternate suffix; left prefix minus right len is the shared phrase
                suffix_len  = len(right_words)
                base_words  = left_words[:-suffix_len] if suffix_len < len(left_words) else left_words[:-1]
                or_terms    = left_words[len(base_words):] + right_words
                what_phrase = " ".join(base_words)
                what_or     = " ".join(or_terms)

            jobs = []
            seen = set()

            for country in countries:
                if len(jobs) >= limit:
                    break

                params = urllib.parse.urlencode({
                    "app_id":           app_id,
                    "app_key":          app_key,
                    "results_per_page": min(limit, 10),
                    "what_phrase":      what_phrase,
                    "what_or":          what_or,
                    "where":            location if location and "emea" not in loc_lower else "",
                    "content-type":     "application/json",
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

                    title_str = item.get("title", "")
                    title_lower = title_str.lower()

                    # Infer seniority from title
                    if any(w in title_lower for w in ["chief", "cto", "cio", "cdo", "vp ", "vice president"]):
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
                    sal_min = item.get("salary_min")
                    sal_max = item.get("salary_max")
                    if sal_min and sal_max:
                        salary = f"£{int(sal_min):,} – £{int(sal_max):,}"
                    elif sal_min:
                        salary = f"£{int(sal_min):,}+"
                    else:
                        salary = ""

                    contract = item.get("contract_type", "")
                    contract_time = item.get("contract_time", "")

                    jobs.append({
                        "id":            job_id,
                        "title":         title_str,
                        "company":       item.get("company", {}).get("display_name", ""),
                        "location":      item.get("location", {}).get("display_name", country.upper()),
                        "description":   item.get("description", ""),
                        "url":           item.get("redirect_url", ""),
                        "posted":        item.get("created", "")[:10] if item.get("created") else "",
                        "salary":        salary,
                        "seniority":     seniority,
                        "contract_type": contract,
                        "contract_time": contract_time,
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
