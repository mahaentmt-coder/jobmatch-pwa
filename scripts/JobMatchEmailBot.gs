/**
 * ╔══════════════════════════════════════════════════════════╗
 * ║           JobMatch AI — Email Bot                        ║
 * ║           Google Apps Script                             ║
 * ╠══════════════════════════════════════════════════════════╣
 * ║  Runs on: maha.jobmatch@gmail.com (dedicated inbox)      ║
 * ║  Reports to: h.mirisaee@gmail.com                        ║
 * ║  Frequency: every 1 hour                                 ║
 * ╠══════════════════════════════════════════════════════════╣
 * ║  SETUP (one-time, ~2 minutes):                           ║
 * ║  1. Go to https://script.google.com → New project        ║
 * ║  2. Paste this entire file, click Save                   ║
 * ║  3. Run testWithSampleJobs() first to authorise & verify ║
 * ║  4. Clock icon → Add Trigger:                            ║
 * ║       Function : checkNewJobAlerts                       ║
 * ║       Event    : Time-driven → Hour timer → Every 1 hour ║
 * ╚══════════════════════════════════════════════════════════╝
 */

// ─────────────────────────────────────────────────────────────────────────────
// CONFIG
// ─────────────────────────────────────────────────────────────────────────────
const CONFIG = {
  RAPIDAPI_KEY : "60f1ad8b3bmsh5c35504cc747bb6p14763cjsne1decca77a34",
  JOBMATCH_URL : "https://jobmatch-pwa.vercel.app/api/match",
  REPORT_TO    : "h.mirisaee@gmail.com",
  LABEL_DONE   : "jm-processed",   // applied to processed threads so they're never re-scored
  MIN_SCORE    : 0,                 // include all jobs in report (sorted by score)
  THROTTLE_MS  : 60 * 60 * 1000,   // 1 hour between runs
};

// ─────────────────────────────────────────────────────────────────────────────
// HADI'S RESUME  (keep in sync with app)
// ─────────────────────────────────────────────────────────────────────────────
const RESUME = `
Hadi Mirisaee — Digital Transformation Programme Leader

EXPERIENCE:
Global Delivery Manager | Capgemini | Netherlands | Mar 2025 – Present
- Lead end-to-end digital transformation programme delivery for regional and global clients, portfolios exceeding €5M
- Design governance and portfolio management frameworks improving delivery predictability and risk visibility
- Advise C-suite leaders on agile operating models, AI-enabled transformation, and cloud-first modernisation strategies
- Manage cross-functional, multi-vendor teams across matrixed global organisations

Program Manager | Macquarie Group (Financial Services) | New York / UK / Australia | Jul 2021 – Jun 2023
- Delivered large-scale AI and GenAI-enabled technology transformation programmes across three continents
- Sole programme delivery accountability for a $10M reinsurance investment programme
- Led multi-workstream programme execution across business, technology, and third-party teams
- Applied: AWS, GenAI delivery, Agile (SAFe/Scrum), Jira/Confluence, budget management, multi-vendor governance, executive stakeholder management

Principal Consultant | TEAL | Australia | Jul 2023 – Jul 2024
- Led global transformation coaching programmes aligning regional delivery operations with UK HQ strategy
- Trusted advisor to C-suite leaders on agile transformation, digital product strategy, and organisational change

Group Product Manager | GP Synergy (Healthcare) | Sydney | Jun 2016 – Jun 2021
- Led enterprise-wide digital transformation to a product-centric, agile delivery model
- Implemented ITIL and cybersecurity frameworks, achieving ISO 27001 certification, reducing incidents by 80%
- Delivered data governance, data warehouse, and operational reporting platforms

Business Systems Analyst | University of the Sunshine Coast | Apr 2014 – Jun 2016
- Adopted Scrum to improve delivery efficiency; built solutions using .NET, C#, Azure DevOps, SQL

EDUCATION:
- Graduate Certificate in Health Data Science — UNSW Australia (2021–2022)
- PhD in Human Computer Interaction — Queensland University of Technology (2010–2014)
- Master of Information Technology — UKM Malaysia (2007–2009)

CERTIFICATIONS:
- Certified SAFe 6 Agilist | PRINCE2 Practitioner | Certified Scrum Product Owner
- IBM Enterprise Design Thinking Practitioner | Life Science Industry Certification L1 (Capgemini)

SKILLS:
Digital Transformation, Programme Delivery, AI Strategy, Cloud Modernisation,
Agile (SAFe/Scrum), Stakeholder Management, Budget Management (€5M+),
Multi-vendor Governance, Data Governance, ITIL, ISO 27001,
Executive Advisory, Portfolio Management, Change Management
`.trim();

// ─────────────────────────────────────────────────────────────────────────────
// SEARCH CONFIGURATION
// ─────────────────────────────────────────────────────────────────────────────
const EMEA_LOCATIONS = [
  // British Isles
  "UK", "Ireland",
  // Benelux
  "Netherlands", "Belgium", "Luxembourg",
  // DACH
  "Germany", "Austria", "Switzerland",
  // Iberia & France
  "France", "Spain", "Portugal",
  // Nordics
  "Denmark", "Sweden", "Norway", "Finland",
  // Eastern Europe
  "Poland", "Czechia",
  // Gulf / Middle East
  "UAE", "Saudi Arabia", "Qatar", "Bahrain", "Kuwait", "Jordan",
  // Africa
  "South Africa", "Egypt", "Morocco",
];

const SEARCH_QUERIES = [
  "Digital Transformation Director or Executive",
  "Programme Director Digital Transformation",
  "AI Digital Transformation Director",
  "IT Program Director or Executive",
  "Strategy Director Digital",
];

// Job titles that indicate a role is too junior or irrelevant
const JUNIOR_TITLE_SIGNALS = [
  "junior", "graduate", "intern", "entry level", "apprentice",
  "assistant", "coordinator", "administrator", "support",
];

// ─────────────────────────────────────────────────────────────────────────────
// MAIN ENTRY POINT  —  triggered every hour by Apps Script
// ─────────────────────────────────────────────────────────────────────────────
function checkNewJobAlerts() {
  // ── Throttle: skip if run less than 1 hour ago
  const props   = PropertiesService.getScriptProperties();
  const lastRun = parseInt(props.getProperty("lastRun") || "0", 10);
  const now     = Date.now();
  if (now - lastRun < CONFIG.THROTTLE_MS) {
    Logger.log(`Skipping — last run was ${Math.round((now - lastRun) / 60000)}m ago (< 1h)`);
    return;
  }
  props.setProperty("lastRun", String(now));

  ensureLabel_();

  // ── Step 1: Extract jobs from unprocessed LinkedIn alert emails
  const threads  = GmailApp.search(`-label:${CONFIG.LABEL_DONE}`, 0, 20);
  const emailJobs = [];
  const titlesSeen = new Set();

  Logger.log(`Found ${threads.length} unprocessed email thread(s)`);

  for (const thread of threads) {
    try {
      const body = thread.getMessages()[0].getPlainBody();
      for (const job of extractJobsFromEmail_(body)) {
        const key = job.title.toLowerCase();
        if (!titlesSeen.has(key)) { titlesSeen.add(key); emailJobs.push(job); }
      }
    } catch (e) { Logger.log(`Email parse error: ${e}`); }
    labelThread_(thread);
  }
  Logger.log(`Jobs extracted from emails: ${emailJobs.length}`);

  // ── Step 2: Proactive JSearch sweep across all 25 EMEA countries
  const sweepJobs = searchJSearch_();
  Logger.log(`Jobs from JSearch sweep: ${sweepJobs.length}`);

  // ── Step 3: Merge — email jobs first, then sweep jobs not already in list
  const merged = [...emailJobs];
  for (const j of sweepJobs) {
    const key = j.title.toLowerCase();
    if (!titlesSeen.has(key)) { titlesSeen.add(key); merged.push(j); }
  }
  Logger.log(`Total unique jobs to score: ${merged.length}`);

  if (!merged.length) { Logger.log("Nothing to score — exiting."); return; }

  // ── Step 4: Score each job against Hadi's resume
  const scored = [];
  for (const j of merged) {
    const desc   = j.desc || fetchDescription_(j.title, j.company, j.location);
    const result = desc
      ? scoreJob_(j.title, j.company, desc)
      : { score: null, rec: "Description not available", gaps: [], strengths: [] };

    scored.push({ ...j, desc: undefined, ...result }); // drop desc from payload
    Logger.log(`  [${result.score ?? "N/A"}] ${j.title} @ ${j.company}`);
    Utilities.sleep(500);
  }

  // ── Step 5: Sort by score and send report
  scored.sort((a, b) => (b.score || 0) - (a.score || 0));
  sendReport_(scored, "Digital Transformation Director/Executive — EMEA");
  Logger.log(`✅ Report sent to ${CONFIG.REPORT_TO} — ${scored.length} jobs`);
}

// ─────────────────────────────────────────────────────────────────────────────
// EXTRACT JOBS FROM LINKEDIN ALERT EMAIL TEXT
// ─────────────────────────────────────────────────────────────────────────────
function extractJobsFromEmail_(text) {
  const jobs  = [];
  const seen  = new Set();
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);

  for (let i = 0; i < lines.length - 1; i++) {
    const line = lines[i];
    const next = lines[i + 1] || "";

    // LinkedIn alert format: Title line → "Company · Location" line
    if (!next.includes(" · ") || line.includes(" · ")) continue;
    if (line.length < 8 || line.length > 130) continue;
    if (/linkedin|gmail|copyright|manage|unsubscribe|learn why|intended for|actively recruiting|easy apply|see all|school alum/i.test(line)) continue;

    const parts    = next.split(" · ");
    const company  = parts[0].trim();
    const location = parts.slice(1).join(", ").trim();

    if (!company || company.length > 80) continue;

    const key = line.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      jobs.push({ title: line, company, location });
      i++; // skip the company·location line
    }
  }
  return jobs;
}

// ─────────────────────────────────────────────────────────────────────────────
// PROACTIVE JSEARCH SWEEP  —  5 queries × 25 EMEA countries
// ─────────────────────────────────────────────────────────────────────────────
function searchJSearch_() {
  const results = [];
  const seen    = new Set();

  for (const query of SEARCH_QUERIES) {
    for (const loc of EMEA_LOCATIONS) {
      try {
        const url  = `https://jsearch.p.rapidapi.com/search?query=${encodeURIComponent(query + " in " + loc)}&page=1&num_pages=2&date_posted=week&employment_types=FULLTIME`;
        const resp = UrlFetchApp.fetch(url, {
          method: "get",
          headers: { "x-rapidapi-host": "jsearch.p.rapidapi.com", "x-rapidapi-key": CONFIG.RAPIDAPI_KEY },
          muteHttpExceptions: true,
        });
        if (resp.getResponseCode() !== 200) continue;

        for (const item of (JSON.parse(resp.getContentText()).data || [])) {
          if (seen.has(item.job_id)) continue;
          seen.add(item.job_id);

          // Skip short descriptions
          if ((item.job_description || "").length < 200) continue;

          // Skip junior titles
          const titleLower = (item.job_title || "").toLowerCase();
          if (JUNIOR_TITLE_SIGNALS.some(s => titleLower.includes(s))) continue;

          // Skip clearly junior salaries (< £/€60k per year)
          if (item.job_min_salary && item.job_salary_period === "YEAR" && parseFloat(item.job_min_salary) < 60000) continue;

          results.push({
            title:    item.job_title,
            company:  item.employer_name,
            location: [item.job_city, item.job_country].filter(Boolean).join(", "),
            desc:     item.job_description,
            url:      item.job_apply_link || item.job_google_link || "",
            salary:   extractSalary_(item.job_title, item.job_description),
          });
        }
        Utilities.sleep(200);
      } catch (e) { Logger.log(`searchJSearch_ error (${query} / ${loc}): ${e}`); }
    }
  }

  Logger.log(`JSearch sweep complete: ${results.length} quality jobs`);
  return results;
}

// ─────────────────────────────────────────────────────────────────────────────
// FETCH DESCRIPTION FOR EMAIL-SOURCED JOBS (no description in email)
// ─────────────────────────────────────────────────────────────────────────────
function fetchDescription_(title, company) {
  try {
    const q    = `${title} ${company}`.replace(/[^\w\s]/g, "").substring(0, 100);
    const resp = UrlFetchApp.fetch(
      `https://jsearch.p.rapidapi.com/search?query=${encodeURIComponent(q)}&page=1&num_pages=2`,
      { method: "get", headers: { "x-rapidapi-host": "jsearch.p.rapidapi.com", "x-rapidapi-key": CONFIG.RAPIDAPI_KEY }, muteHttpExceptions: true }
    );
    if (resp.getResponseCode() !== 200) return null;

    const jobs = JSON.parse(resp.getContentText()).data || [];
    const co   = company.toLowerCase().split(" ")[0];

    // Prefer same company, then any job with a decent description
    const best = jobs.find(j => j.employer_name?.toLowerCase().includes(co) && j.job_description?.length > 200)
              || jobs.find(j => j.job_description?.length > 200);
    return best?.job_description || null;
  } catch (e) {
    Logger.log(`fetchDescription_ error: ${e}`);
    return null;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SALARY EXTRACTOR  —  parses £/€/$ ranges from title + description text
// ─────────────────────────────────────────────────────────────────────────────
function extractSalary_(title, description) {
  const sources = [title || "", (description || "").substring(0, 2000)];
  const re      = /(£|€|\$|USD|EUR|GBP)?\s*(\d[\d,\.]+)\s*[kK]?\s*(?:[-–to]+\s*(£|€|\$)?\s*(\d[\d,\.]+)\s*[kK]?)?/gi;

  for (const src of sources) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(src)) !== null) {
      const raw  = m[0].trim();
      const val  = parseFloat(m[2].replace(/[,\.]/g, ""));
      if (isNaN(val)) continue;
      const norm = /k/i.test(raw) && val < 1000 ? val * 1000 : val;
      if ((m[1] || norm >= 30000) && norm >= 20000 && norm <= 1000000) return raw;
    }
  }
  return "";
}

// ─────────────────────────────────────────────────────────────────────────────
// SCORE JOB VIA JOBMATCH API  (Claude Haiku)
// ─────────────────────────────────────────────────────────────────────────────
function scoreJob_(title, company, description) {
  try {
    const resp = UrlFetchApp.fetch(CONFIG.JOBMATCH_URL, {
      method:             "post",
      contentType:        "application/json",
      payload:            JSON.stringify({
        resume_text:     RESUME,
        job_title:       title,
        company:         company,
        job_description: description.substring(0, 3000),
      }),
      muteHttpExceptions: true,
    });
    if (resp.getResponseCode() !== 200) return { score: null, rec: "API error", gaps: [], strengths: [] };
    const d = JSON.parse(resp.getContentText());
    return {
      score:     d.match_score      || 0,
      rec:       d.recommendation   || "",
      gaps:      d.missing_keywords || [],
      strengths: d.strengths        || [],
    };
  } catch (e) {
    Logger.log(`scoreJob_ error: ${e}`);
    return { score: null, rec: "Error", gaps: [], strengths: [] };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SEND HTML REPORT EMAIL
// ─────────────────────────────────────────────────────────────────────────────
function sendReport_(jobs, subject) {
  const scored      = jobs.filter(j => j.score !== null);
  const topScore    = scored.length ? Math.max(...scored.map(j => j.score)) : 0;
  const strongCount = scored.filter(j => j.score >= 75).length;
  const date        = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  // ── Job cards
  const cardRows = jobs.map((j, idx) => {
    const s        = j.score;
    const hasScore = s !== null;
    const border   = !hasScore ? "#334155" : s >= 75 ? "#10b981" : s >= 55 ? "#f59e0b" : "#ef4444";
    const badgeBg  = !hasScore ? "#1e293b" : s >= 75 ? "rgba(16,185,129,0.15)" : s >= 55 ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.12)";
    const badgeClr = !hasScore ? "#64748b" : s >= 75 ? "#10b981" : s >= 55 ? "#f59e0b" : "#ef4444";
    const verdict  = !hasScore  ? "⚠️ Description not found"
                   : s >= 75   ? "✅ Strong match — apply with tailoring"
                   : s >= 55   ? "🟡 Decent fit — tailor carefully"
                                : "❌ Weak match — skip";

    const strTags = (j.strengths || []).slice(0, 3).map(t =>
      `<span style="display:inline-block;background:rgba(16,185,129,0.1);color:#6ee7b7;font-size:11px;padding:2px 8px;border-radius:4px;margin:2px 2px 0 0">${t}</span>`
    ).join("");
    const gapTags = (j.gaps || []).slice(0, 4).map(t =>
      `<span style="display:inline-block;background:#1e3a5f;color:#94a3b8;font-size:11px;padding:2px 8px;border-radius:4px;margin:2px 2px 0 0">${t}</span>`
    ).join("");

    const applyBtn = j.url
      ? `<a href="${j.url}" style="display:inline-block;margin-top:10px;background:rgba(59,130,246,0.15);color:#60a5fa;text-decoration:none;padding:6px 14px;border-radius:6px;font-size:12px;border:1px solid rgba(59,130,246,0.3)">🔗 Apply</a>`
      : "";

    return `
    <tr><td style="padding:0 0 14px 0">
      <div style="background:#0f172a;border:1px solid ${border}50;border-left:3px solid ${border};border-radius:10px;padding:16px">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="vertical-align:top">
            <div style="font-size:11px;font-weight:600;color:#475569;letter-spacing:1px;margin-bottom:4px">#${idx + 1}</div>
            <div style="font-size:15px;font-weight:700;color:#f1f5f9;line-height:1.3;margin-bottom:3px">${j.title}</div>
            <div style="font-size:12px;color:#64748b">${j.company || ""}${j.location ? " · " + j.location : ""}</div>
          </td>
          <td style="vertical-align:top;text-align:right;padding-left:12px;width:56px">
            <div style="width:52px;height:52px;border-radius:50%;background:${badgeBg};border:2px solid ${border};display:inline-flex;align-items:center;justify-content:center;flex-direction:column">
              <div style="font-size:${hasScore ? "20" : "11"}px;font-weight:700;color:${badgeClr};font-family:monospace;line-height:1">${hasScore ? s : "N/A"}</div>
            </div>
          </td>
        </tr></table>
        <div style="margin-top:8px;font-size:12px;color:#94a3b8">${verdict}</div>
        ${j.salary ? `<div style="margin-top:6px"><span style="background:rgba(16,185,129,0.1);color:#6ee7b7;font-size:12px;font-weight:600;padding:3px 10px;border-radius:6px;border:1px solid rgba(16,185,129,0.2)">💰 ${j.salary}</span></div>` : ""}
        ${strTags ? `<div style="margin-top:8px">${strTags}</div>` : ""}
        ${gapTags ? `<div style="margin-top:6px;font-size:11px;color:#475569">Missing: ${gapTags}</div>` : ""}
        ${applyBtn}
      </div>
    </td></tr>`;
  }).join("");

  // ── Full HTML email
  const html = `<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#060b18;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:640px;margin:0 auto;padding:24px 16px">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#0f172a,#1e293b);border:1px solid #1e3a5f;border-radius:16px;padding:28px;margin-bottom:20px">
    <div style="font-size:24px;font-weight:800;color:#3b82f6;margin-bottom:4px">🎯 JobMatch AI</div>
    <div style="font-size:13px;color:#475569;margin-bottom:20px">${date} · Powered by Claude AI</div>

    <!-- Stats row -->
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="width:33%;padding-right:8px">
        <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:28px;font-weight:700;color:#10b981;font-family:monospace">${topScore}</div>
          <div style="font-size:10px;color:#64748b;letter-spacing:1px;margin-top:2px">TOP SCORE</div>
        </div>
      </td>
      <td style="width:33%;padding-right:8px">
        <div style="background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.25);border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:28px;font-weight:700;color:#3b82f6;font-family:monospace">${strongCount}</div>
          <div style="font-size:10px;color:#64748b;letter-spacing:1px;margin-top:2px">STRONG MATCHES</div>
        </div>
      </td>
      <td style="width:33%">
        <div style="background:rgba(255,255,255,0.03);border:1px solid #1e3a5f;border-radius:10px;padding:12px;text-align:center">
          <div style="font-size:28px;font-weight:700;color:#94a3b8;font-family:monospace">${jobs.length}</div>
          <div style="font-size:10px;color:#64748b;letter-spacing:1px;margin-top:2px">JOBS SCORED</div>
        </div>
      </td>
    </tr></table>
  </div>

  <!-- Job cards -->
  <table width="100%" cellpadding="0" cellspacing="0">${cardRows}</table>

  <!-- Footer CTA -->
  <div style="text-align:center;padding:16px 0 8px">
    <a href="https://jobmatch-pwa.vercel.app" style="display:inline-block;background:linear-gradient(135deg,#3b82f6,#06b6d4);color:#fff;text-decoration:none;padding:14px 32px;border-radius:12px;font-weight:700;font-size:14px;letter-spacing:0.5px">
      Open JobMatch AI →
    </a>
    <div style="margin-top:14px;font-size:11px;color:#1e3a5f">
      Auto-scored by JobMatch AI · Sent to ${CONFIG.REPORT_TO}
    </div>
  </div>

</div></body></html>`;

  GmailApp.sendEmail(CONFIG.REPORT_TO, `🎯 JobMatch Report — ${subject}`, "", { htmlBody: html });
}

// ─────────────────────────────────────────────────────────────────────────────
// GMAIL HELPERS
// ─────────────────────────────────────────────────────────────────────────────
function ensureLabel_() {
  if (!GmailApp.getUserLabels().some(l => l.getName() === CONFIG.LABEL_DONE)) {
    GmailApp.createLabel(CONFIG.LABEL_DONE);
  }
}

function labelThread_(thread) {
  const label = GmailApp.getUserLabelByName(CONFIG.LABEL_DONE);
  if (label) label.addToThread(thread);
}

// ─────────────────────────────────────────────────────────────────────────────
// MANUAL TEST  —  run this once after pasting to verify everything works
// Sends a scored report to h.mirisaee@gmail.com using the 6 sample jobs
// ─────────────────────────────────────────────────────────────────────────────
function testWithSampleJobs() {
  Logger.log("=== JobMatch Test Run ===");

  const sampleJobs = [
    { title: "Global Digital & AI Transformation Director Program Management", company: "Arcadis",                   location: "Amsterdam, Netherlands" },
    { title: "Technology Transformation Director (Target Operating Model)",    company: "Intec Select",              location: "London, UK"             },
    { title: "Head of Digitalization",                                         company: "Madison Pearl",             location: "Dubai, UAE"             },
    { title: "Director General for Digital Transformation & Coach",            company: "Impel-Consultants",         location: "UK"                     },
    { title: "Transformation Program Director (AI & Digital Transformation)",  company: "Ingenio Global",            location: "Dublin, Ireland"        },
    { title: "Transformation Management Lead - Principal",                     company: "Apollo Global Management",  location: "London, UK"             },
  ];

  const scored = [];
  for (const job of sampleJobs) {
    Logger.log(`Fetching: ${job.title}`);
    const desc   = fetchDescription_(job.title, job.company);
    const salary = desc ? extractSalary_(job.title, desc) : "";
    const result = desc
      ? scoreJob_(job.title, job.company, desc)
      : { score: null, rec: "No description found", gaps: [], strengths: [] };
    scored.push({ ...job, salary, ...result });
    Logger.log(`  → Score: ${result.score} | ${result.rec}`);
    Utilities.sleep(700);
  }

  scored.sort((a, b) => (b.score || 0) - (a.score || 0));
  sendReport_(scored, "Test Report — Sample Jobs");
  Logger.log(`Test complete — report sent to ${CONFIG.REPORT_TO}`);
}
