from http.server import BaseHTTPRequestHandler
import json, os, urllib.request

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"  # Sonnet for higher quality tailoring


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

            if not resume_text or not job_description:
                self._json({"error": "resume_text and job_description are required"}, 400)
                return

            prompt = f"""You are an expert CV writer and career coach. Rewrite the candidate's CV summary and top bullet points 
to maximise ATS score and relevance for the job below. Use the job's exact language and keywords throughout.

CANDIDATE RESUME:
{resume_text[:3500]}

TARGET JOB TITLE: {job_title}
TARGET COMPANY: {company}
JOB DESCRIPTION:
{job_description[:2500]}

Respond ONLY with a valid JSON object (no markdown, no preamble, no backticks):
{{
  "tailored_summary": "<rewritten 4-5 sentence professional summary packed with job keywords>",
  "tailored_bullets": [
    "<rewritten bullet 1 — quantified, keyword-rich, starts with strong verb>",
    "<rewritten bullet 2>",
    "<rewritten bullet 3>",
    "<rewritten bullet 4>",
    "<rewritten bullet 5>"
  ],
  "keywords_added": ["keyword1","keyword2","keyword3","keyword4","keyword5"],
  "cover_letter": "<professional 4-paragraph cover letter addressed to {company} hiring team, persuasive, no fluff>"
}}"""

            result = self._call_claude(prompt, max_tokens=2000)
            data = json.loads(result)
            self._json(data)

        except json.JSONDecodeError as e:
            self._json({"error": f"Failed to parse AI response: {str(e)}"}, 500)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _call_claude(self, prompt: str, max_tokens: int = 2000) -> str:
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
        with urllib.request.urlopen(req, timeout=45) as resp:
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
