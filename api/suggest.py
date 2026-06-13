from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL         = "claude-haiku-4-5-20251001"


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            resume = body.get("resume_text", "").strip()

            if not resume:
                self._json({"error": "resume_text required"}, 400)
                return

            prompt = f"""You are a senior executive recruiter. Based on this candidate's CV, generate exactly 6 optimised job search query strings for a job board (LinkedIn/Indeed).

CV:
{resume[:3000]}

Rules:
- Each query must target Director, Head of, VP, or C-suite level roles — the candidate's target seniority
- Queries must reflect their ACTUAL skills and experience — not generic titles
- Each query should be distinct — cover different angles (transformation, delivery, AI/data, consulting, strategy, product)
- Use job-board-style phrasing: short, keyword-rich, no full sentences
- Format: "Title OR Synonym keyword" — e.g. "Director OR Head Digital Transformation AI"
- Each query: 4-8 words max
- Do NOT include location — that is handled separately

Respond ONLY with a valid JSON array of exactly 6 strings, no markdown, no preamble:
["query 1", "query 2", "query 3", "query 4", "query 5", "query 6"]"""

            result  = self._call_claude(prompt)
            queries = self._extract_json_array(result)

            if not isinstance(queries, list) or len(queries) < 2:
                raise ValueError(f"Unexpected response: {result[:200]}")

            self._json({"queries": queries[:8]})

        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _extract_json_array(self, text):
        start = text.find('[')
        end   = text.rfind(']')
        if start == -1 or end == -1:
            raise ValueError(f"No JSON array in response: {text[:200]}")
        return json.loads(text[start:end+1])

    def _call_claude(self, prompt):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        payload = json.dumps({
            "model":      MODEL,
            "max_tokens": 400,
            "messages":   [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())["content"][0]["text"]

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if self.command == "OPTIONS":
            self.send_response(200)
            self.end_headers()
