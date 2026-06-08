from http.server import BaseHTTPRequestHandler
import json, os, urllib.request, urllib.error

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL         = "claude-sonnet-4-6"

# Static CV sections that don't change
EDUCATION = [
    {"degree": "Graduate Certificate in Health Data Science", "school": "UNSW, Australia", "years": "2021 – 2022"},
    {"degree": "PhD in Human Computer Interaction",           "school": "Queensland University of Technology", "years": "2010 – 2014"},
    {"degree": "Master of Information Technology",            "school": "UKM, Malaysia", "years": "2007 – 2009"},
]

CERTIFICATIONS = [
    "Certified SAFe 6 Agilist — Scaled Agile | Sep 2024",
    "PRINCE2 Practitioner — PeopleCert | Jan 2021",
    "Scrum Alliance Certified Scrum Product Owner — Scrum Alliance | Jun 2018",
    "IBM Enterprise Design Thinking Practitioner — IBM | Sep 2021",
    "Life Science Industry Certification — L1 — Capgemini | May 2025",
]

EXPERIENCE = [
    {
        "title":   "Global Delivery Manager",
        "company": "Capgemini",
        "location":"Netherlands",
        "dates":   "Mar 2025 – Present",
        "bullets": [
            "Lead end-to-end digital transformation programme delivery for regional and global clients across portfolios exceeding €5M, with full accountability for delivery quality, timelines, and executive reporting.",
            "Design governance and portfolio management frameworks that improve delivery predictability, risk visibility, and steering committee decision-making.",
            "Advise C-suite leaders on agile operating models, AI-enabled transformation, and cloud-first modernisation strategies.",
            "Manage cross-functional, multi-vendor teams across matrixed global organisations, ensuring clear ownership and delivery accountability at every workstream level.",
        ]
    },
    {
        "title":   "Program Manager ★ Key Role",
        "company": "Macquarie Group (Financial Services)",
        "location":"New York — USA / UK / Australia",
        "dates":   "Jul 2021 – Jun 2023",
        "bullets": [
            "Delivered large-scale AI and GenAI-enabled technology transformation programmes across three continents in a highly regulated, high-stakes financial services environment — spanning reinsurance, investment operations, and digital platforms.",
            "Sole programme delivery accountability for a $10M reinsurance investment programme, managing budget, vendor relationships, cross-functional teams, and executive stakeholders across the USA, UK, and Australia simultaneously.",
            "Led multi-workstream programme execution across business, technology, and third-party teams — managing dependencies, escalating risks, and ensuring delivery to plan in a fast-moving, low-tolerance environment.",
            "Facilitated executive workshops and steering committee reporting, translating complex programme status into clear, decision-ready insight for senior leadership.",
            "Drove automation, scalability, and operational efficiency outcomes with measurable post-delivery benefits realisation.",
            "Applied: AWS, GenAI delivery, Agile (SAFe/Scrum), Jira/Confluence, budget management, multi-vendor governance, executive stakeholder management",
        ]
    },
    {
        "title":   "Principal Consultant",
        "company": "TEAL",
        "location":"Australia",
        "dates":   "Jul 2023 – Jul 2024",
        "bullets": [
            "Led global transformation coaching programmes aligning regional delivery operations with UK HQ strategy.",
            "Acted as trusted advisor to C-suite leaders on agile transformation, digital product strategy, and organisational change.",
        ]
    },
    {
        "title":   "Group Product Manager",
        "company": "GP Synergy (Healthcare Organisation)",
        "location":"Sydney",
        "dates":   "Jun 2016 – Jun 2021",
        "bullets": [
            "Led enterprise-wide digital transformation to a product-centric, agile delivery model across a regulated healthcare organisation.",
            "Implemented ITIL and cybersecurity frameworks, achieving ISO 27001 certification and reducing security incidents by 80%.",
            "Delivered data governance, data warehouse, and operational reporting platforms — managing vendors, stakeholders, and cross-functional delivery teams.",
        ]
    },
    {
        "title":   "Business Systems Analyst",
        "company": "University of the Sunshine Coast",
        "location":"Sunshine Coast",
        "dates":   "Apr 2014 – Jun 2016",
        "bullets": [
            "Adopted Scrum methodology to improve delivery efficiency; built high-performance web solutions using .NET, C#, Azure DevOps, and SQL.",
        ]
    },
]


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self._cors()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))

            job_title       = body.get("job_title", "")
            company         = body.get("company", "")
            job_description = body.get("job_description", "")

            if not job_description:
                self._json({"error": "job_description required"}, 400)
                return

            prompt = f"""You are an expert CV writer and career coach. Tailor Hadi Mirisaee's application for this specific job.

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION:
{job_description[:3000]}

HADI'S CURRENT EXPERIENCE:
{json.dumps(EXPERIENCE, indent=2)[:3000]}

Return ONLY a valid JSON object with this exact structure:
{{
  "headline": "<tailored 1-line title e.g. Digital Transformation Director | Programme Delivery | AI & Cloud>",
  "summary": "<tailored 4-5 sentence professional summary using job's exact language and keywords>",
  "experience": [
    {{
      "title": "<same job title>",
      "company": "<same company>",
      "location": "<same location>",
      "dates": "<same dates>",
      "bullets": ["<rewritten bullet 1 with job keywords>", "<bullet 2>", "..."]
    }}
  ],
  "skills": {{
    "Programme Delivery": "<tailored skill description>",
    "Digital Transformation": "<tailored skill description>",
    "Agile at Scale": "<tailored skill description>",
    "Stakeholder Management": "<tailored skill description>",
    "AI & Cloud Strategy": "<tailored skill description>"
  }},
  "cover_letter": "<3 short punchy paragraphs, NO 'Dear Hiring Manager' opener — start with a bold hook sentence about Hadi's value for THIS role. Para 1: hook + why this role. Para 2: 2-3 specific achievements that directly answer the JD requirements (use numbers). Para 3: confident closing with a call to action. Max 200 words total. No clichés. No 'I am writing to apply'.>"
}}

Rules:
- Keep all 5 experience roles, same companies/dates/locations
- Rewrite bullets to mirror the job's language and priorities
- Keep bullets concise and quantified where possible
- The headline and summary must use the job's exact keywords
- Cover letter must be punchy, specific, and read like it was written by a confident senior executive"""

            result = self._call_claude(prompt)
            data   = json.loads(self._extract_json(result))

            # Merge static sections
            data["education"]       = EDUCATION
            data["certifications"]  = CERTIFICATIONS
            data["name"]            = "Hadi Mirisaee"
            data["contact"]         = "+31 6 2937 2570 | h.mirisaee@gmail.com | Netherlands (open to relocation — Dublin)"
            data["job_title"]       = job_title
            data["company"]         = company

            self._json(data)

        except json.JSONDecodeError as e:
            self._json({"error": f"Failed to parse AI response: {str(e)}"}, 500)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _extract_json(self, text):
        start = text.find('{')
        end   = text.rfind('}')
        if start == -1 or end == -1:
            raise ValueError(f"No JSON in response: {text[:200]}")
        return text[start:end+1]

    def _call_claude(self, prompt):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        payload = json.dumps({
            "model":      MODEL,
            "max_tokens": 3000,
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
        with urllib.request.urlopen(req, timeout=45) as resp:
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if self.command == "OPTIONS":
            self.send_response(200)
            self.end_headers()
