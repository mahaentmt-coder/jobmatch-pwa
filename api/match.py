from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"  # Fast + cheap for scoring


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            resume_text     = body.get("resume_text", "")
            job_description = body.get("job_description", "")
            job_title       = body.get("job_title", "")
            company         = body.get("company", "")
            job_id          = body.get("job_id", "manual")

            if not resume_text or not job_description:
                self._json({"error": "resume_text and job_description are required"}, 400)
                return

            prompt = f"""You are a senior recruiter scoring a candidate's CV against a job description.
The candidate is Hadi Mirisaee — a Director/Executive-level Digital Transformation leader.
His target level is Director, Head of, VP, or equivalent senior leadership roles.

CANDIDATE CV (first 3000 chars):
{resume_text[:3000]}

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION (first 2500 chars):
{job_description[:2500]}

SCORING RULES — apply strictly:
- Start at 50. Add/subtract points based on the criteria below.
- Seniority match: +20 if the role is Director/Head/VP/Principal/Partner level. -20 if it is Senior Manager or below (PM, Senior PM, Manager, Team Lead, etc.). These are NOT the right level for this candidate.
- Skills match: up to +20 for direct skill overlap (digital transformation, programme delivery, AI, cloud, agile, stakeholder management, etc.)
- Industry/domain fit: up to +10 for relevant industry (financial services, tech, consulting, healthcare)
- Location/remote fit: up to +5 if location is EMEA and open/remote
- Deal-breakers: -15 if non-English language is REQUIRED; -10 if the role is clearly technical/hands-on engineering (not leadership)

The score MUST meaningfully differentiate roles. A Senior PM role must score LOWER than a Director role. Never give the same score to clearly different job levels.

Respond ONLY with a valid JSON object (no markdown, no preamble, no backticks).
ALL array fields MUST contain real values — never return empty arrays.

{{
  "match_score": <integer 0-100 — must reflect seniority match strictly>,
  "matched_keywords": ["<5-7 specific skills/keywords from the JD that ARE in the resume>"],
  "missing_keywords": ["<4-6 specific skills/keywords from the JD that are NOT in the resume>"],
  "strengths": ["<3-4 specific strengths Hadi brings for this exact role>"],
  "gaps": ["<2-4 honest gaps or reasons this role may not be right>"],
  "recommendation": "<one of: Apply now | Apply with tailoring | Skip>"
}}"""

            result = self._call_claude(prompt, max_tokens=1200)
            data = json.loads(self._extract_json(result))
            data["job_id"] = job_id
            data["job_title"] = job_title
            data["company"] = company
            self._json(data)

        except json.JSONDecodeError as e:
            self._json({"error": f"Failed to parse AI response: {str(e)}"}, 500)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _extract_json(self, text: str) -> str:
        """Strip any text before/after the JSON object."""
        start = text.find('{')
        end   = text.rfind('}')
        if start == -1 or end == -1:
            raise ValueError(f"No JSON found in response: {text[:200]}")
        return text[start:end+1]

    def _call_claude(self, prompt: str, max_tokens: int = 800) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        payload = json.dumps({
            "model": MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]

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
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if self.command == "OPTIONS":
            self.send_response(200)
            self.end_headers()
