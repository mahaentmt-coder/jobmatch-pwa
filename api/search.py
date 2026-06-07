from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.parse, urllib.error

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"

# Maps location keywords → (country_code, city_filter)
# country_code = Adzuna endpoint; city_filter = `where` param (empty = whole country)
LOCATION_MAP = [
    # Countries — use endpoint only, no city filter
    (["uk", "united kingdom", "britain", "england", "scotland", "wales"], "gb", ""),
    (["netherlands", "holland"],                                           "nl", ""),
    (["germany", "deutschland"],                                           "de", ""),
    (["france"],                                                           "fr", ""),
    (["uae", "united arab emirates"],                                      "ae", ""),
    (["south africa"],                                                     "za", ""),
    (["singapore"],                                                        "sg", ""),
    (["australia"],                                                        "au", ""),
    (["canada"],                                                           "ca", ""),
    (["usa", "united states", "america"],                                  "us", ""),
    (["india"],                                                            "in", ""),
    # Cities — use nearest country endpoint + city filter
    (["london"],                                                           "gb", "London"),
    (["manchester"],                                                       "gb", "Manchester"),
    (["amsterdam"],                                                        "nl", "Amsterdam"),
    (["berlin"],                                                           "de", "Berlin"),
    (["munich", "münchen"],                                                "de", "Munich"),
    (["paris"],                                                            "fr", "Paris"),
    (["dubai"],                                                            "ae", "Dubai"),
    (["sydney"],                                                           "au", "Sydney"),
    (["toronto"],                                                          "ca", "Toronto"),
    (["new york", "nyc"],                                                  "us", "New York"),
]

EMEA_COUNTRIES = ["gb", "de", "fr", "nl", "ae", "za"]


def resolve_location(location: str):
    """Returns list of (country_code, city_filter) tuples to search."""
    if not location:
        return [(c, "") for c in EMEA_COUNTRIES]

    loc = location.lower().strip()

    # EMEA / global → search all EMEA countries
    if any(k in loc for k in ["emea", "worldwide", "global", "remote", "anywhere"]):
        return [(c, "") for c in EMEA_COUNTRIES]

    # Try to match known locations
    for keywords, country, city in LOCATION_MAP:
        if any(k in loc for k in keywords):
            return [(country, city)]

    # Unknown location — search EMEA but pass location as city hint in gb
    return [(c, "") for c in EMEA_COUNTRIES]


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

            # Parse OR queries: "Digital Transformation Director or Executive"
            # → what_phrase="Digital Transformation", what_or="Director Executive"
            what_phrase = title
            what_or     = ""
            if " or " in title.lower():
                idx         = title.lower().index(" or ")
                left        = title[:idx].strip()
                right       = title[idx+4:].strip()
                left_words  = left.split()
                right_words = right.split()
                suffix_len  = len(right_words)
                base_words  = left_words[:-suffix_len] if suffix_len < len(left_words) else left_words[:-1]
                or_terms    = left_words[len(base_words):] + right_words
                what_phrase = " ".join(base_words)
                what_or     = " ".join(or_terms)

            targets = resolve_location(location)
            jobs    = []
            seen    = set()

            for country, city in targets:
                if len(jobs) >= limit:
                    break

                p = {
                    "app_id":           app_id,
                    "app_key":          app_key,
                    "results_per_page": min(limit, 10),
                    "what_phrase":      what_phrase,
                }
                if what_or:
                    p["what_or"] = what_or
                if city:
                    p["where"] = city

                url = f"{ADZUNA_BASE}/{country}/search/1?{urllib.parse.urlencode(p)}"
                req = urllib.request.Request(url, method="GET")

                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read())
                except urllib.error.HTTPError:
                    continue

                for item in data.get("results", []):
                    job_id = str(item.get("id", ""))
                    if job_id in seen:
                        continue
                    seen.add(job_id)

                    title_str   = item.get("title", "")
                    title_lower = title_str.lower()

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

                    sal_min = item.get("salary_min")
                    sal_max = item.get("salary_max")
                    # Format salary with local currency symbol
                    symbols = {"gb": "£", "de": "€", "fr": "€", "nl": "€", "ae": "AED ", "za": "R", "us": "$", "au": "A$", "ca": "C$"}
                    sym = symbols.get(country, "")
                    if sal_min and sal_max:
                        salary = f"{sym}{int(sal_min):,} – {sym}{int(sal_max):,}"
                    elif sal_min:
                        salary = f"{sym}{int(sal_min):,}+"
                    else:
                        salary = ""

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
                        "contract_type": item.get("contract_type", ""),
                        "contract_time": item.get("contract_time", ""),
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
