from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.parse, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

RAPIDAPI_HOST = "jsearch.p.rapidapi.com"
RAPIDAPI_URL  = f"https://{RAPIDAPI_HOST}/search"

EMEA_LOCATIONS = ["UK", "UAE", "Germany", "Netherlands", "Switzerland", "Ireland", "Belgium"]

# Only keep jobs from trusted, high-quality publishers
TRUSTED_PUBLISHERS = {
    "linkedin", "indeed", "glassdoor", "ziprecruiter", "monster",
    "reed", "totaljobs", "cwjobs", "jobsite", "cv-library",
    "michaelpage", "hays", "robertwalters", "robert walters",
    "manpower", "randstad", "adecco", "stepstone", "xing",
    "bayt", "naukrigulf", "experteer", "efinancialcareers",
    "jobs.ac.uk", "guardian jobs", "the guardian",
}

def is_trusted_publisher(publisher: str) -> bool:
    """Return True if publisher is a known quality source."""
    if not publisher:
        return True  # no publisher info → keep (likely direct from employer)
    p = publisher.lower()
    return any(t in p for t in TRUSTED_PUBLISHERS)

# Patterns that indicate a non-English language is REQUIRED
# Matches things like "Dutch required", "fluent in German", "native French speaker"
import re
LANGUAGE_REQUIRED_PATTERNS = re.compile(
    r'\b('
    r'dutch|nederlands|nederlandstalig|'
    r'german|deutsch|deutschkenntnisse|'
    r'french|français|francophone|'
    r'arabic|عربي|'
    r'spanish|español|'
    r'italian|italiano|'
    r'portuguese|português|'
    r'mandarin|chinese|'
    r'japanese|hindi|'
    r'polish|swedish|danish|norwegian|finnish|turkish'
    r')\b.{0,60}\b(required|mandatory|must|essential|vereist|verplicht|zwingend|erforderlich|exigé|nécessaire|fluent|native|proficient|spoken|written|speaking)\b'
    r'|'
    r'\b(fluent|native|proficient|working proficiency|business level)\b.{0,40}\b('
    r'dutch|german|french|arabic|spanish|italian|portuguese|mandarin|japanese|polish|swedish|danish|norwegian|finnish|turkish'
    r')\b',
    re.IGNORECASE
)

# Patterns that indicate language is optional (negate the match)
LANGUAGE_OPTIONAL_PATTERNS = re.compile(
    r'\b(plus|advantage|bonus|preferred|not required|not mandatory|nice to have|pre|desirable)\b',
    re.IGNORECASE
)

def extract_salary(title: str, description: str, structured_salary: str) -> str:
    """Extract salary from structured fields first, then title, then description text."""
    if structured_salary:
        return structured_salary

    # Check title first (e.g. "Programme Director | €170k")
    for text in [title, description[:2000]]:
        if not text:
            continue
        # Patterns: £120k-£150k  €150,000–€200,000  $200k  £80,000 - £100,000  150k-180k
        m = re.search(
            r'(£|€|\$|USD|EUR|GBP)?\s*(\d[\d,\.]+)\s*[kK]?\s*(?:[-–to]+\s*(£|€|\$)?\s*(\d[\d,\.]+)\s*[kK]?)?'
            r'(?:\s*(?:per\s+year|pa|p\.a\.|/\s*year|annually|annual|salary))?',
            text, re.IGNORECASE
        )
        if m:
            raw = m.group(0).strip()
            # Filter out noise: must contain currency symbol or be >= 30k
            val_str = m.group(2).replace(',', '').replace('.', '')
            try:
                val = float(val_str)
                if m.group(1) or val >= 30000 or (val >= 30 and 'k' in raw.lower()):
                    # Normalise "k" values
                    if val < 1000 and 'k' in raw.lower():
                        val = int(val * 1000)
                    # Only return if looks like a salary (20k-500k range)
                    if 20000 <= val <= 1000000:
                        return raw.strip()
            except ValueError:
                pass
    return ""


def requires_non_english(description: str) -> bool:
    """Return True if the job description requires a non-English language."""
    if not description:
        return False
    for match in LANGUAGE_REQUIRED_PATTERNS.finditer(description):
        # Check surrounding context (80 chars) for optional language indicators
        start  = max(0, match.start() - 80)
        end    = min(len(description), match.end() + 80)
        context = description[start:end]
        if not LANGUAGE_OPTIONAL_PATTERNS.search(context):
            return True
    return False


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs     = urllib.parse.parse_qs(parsed.query)

            title    = qs.get("title",    [""])[0].strip()
            location = qs.get("location", [""])[0].strip()
            limit    = int(qs.get("limit", ["50"])[0])

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
                params = urllib.parse.urlencode({
                    "query":            query,
                    "page":             "1",
                    "num_pages":        "3",
                    "date_posted":      "week",
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

                # Skip low-quality aggregator sources
                if not is_trusted_publisher(item.get("job_publisher", "")):
                    continue

                # Skip jobs that require a non-English language
                if requires_non_english(item.get("job_description", "")):
                    continue

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
                sal_min  = item.get("job_min_salary")
                sal_max  = item.get("job_max_salary")
                period   = item.get("job_salary_period", "")
                currency = item.get("job_salary_currency", "")
                if sal_min and sal_max:
                    structured = f"{currency} {int(sal_min):,} – {int(sal_max):,}".strip()
                    if period:
                        structured += f" / {period.lower()}"
                elif sal_min:
                    structured = f"{currency} {int(sal_min):,}+".strip()
                    if period:
                        structured += f" / {period.lower()}"
                else:
                    structured = ""
                salary = extract_salary(title_str, item.get("job_description", ""), structured)

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
