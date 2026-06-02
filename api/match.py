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

            prompt = f"""You are an expert ATS and recruitment specialist. Analyse the resume against the job description.

RESUME (first 3000 chars):
{resume_text[:3000]}

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION (first 2500 chars):
{job_description[:2500]}

Respond ONLY with a valid JSON object (no markdown, no preamble, no backticks):
{{
  "match_score": <integer 0-100>,
  "matched_keywords": ["kw1","kw2","kw3","kw4","kw5"],
  "missing_keywords": ["kw1","kw2","kw3","kw4"],
  "strengths": ["strength1","strength2","strength3"],
  "gaps": ["gap1","gap2"],
  "recommendation": "Apply now|Apply with tailoring|Skip"
}}"""

            result = self._call_claude(prompt, max_tokens=800)
            data = json.loads(result)
            data["job_id"] = job_id
            data["job_title"] = job_title
            data["company"] = company
            self._json(data)

        except json.JSONDecodeError as e:
            self._json({"error": f"Failed to parse AI response: {str(e)}"}, 500)
        except Exception as e:
            self._json({"error": str(e)}, 500)

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
