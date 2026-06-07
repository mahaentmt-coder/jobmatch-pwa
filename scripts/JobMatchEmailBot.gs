/**
 * JobMatch Email Bot — Google Apps Script
 * ─────────────────────────────────────────
 * Watches Gmail for LinkedIn job alert emails, scores every job
 * against Hadi's resume via JobMatch AI, and sends back a report.
 *
 * SETUP (one-time, ~2 minutes):
 *  1. Go to https://script.google.com → New project
 *  2. Paste this entire file
 *  3. Click the clock icon → Add trigger:
 *       Function: checkNewJobAlerts
 *       Event:    Time-driven → Hour timer → Every 1 hour
 *  4. Save & Authorize
 */

// ── CONFIG ────────────────────────────────────────────────────────────────────
const CONFIG = {
  RAPIDAPI_KEY:   "60f1ad8b3bmsh5c35504cc747bb6p14763cjsne1decca77a34",
  JOBMATCH_URL:   "https://jobmatch-pwa.vercel.app/api/match",
  REPORT_TO:      "h.mirisaee@gmail.com",   // report sent to your main inbox
  MIN_SCORE:      60,
  LABEL_DONE:     "jm-processed",
  // This script runs on maha.jobmatch@gmail.com — a dedicated inbox that
  // only receives forwarded LinkedIn job alert emails. No other emails exist
  // here so no sender filter is needed; we just skip already-processed ones.
};

// Hadi's resume (kept in sync with the app)
const RESUME = `
Hadi Mirisaee — Digital Transformation Programme Leader

EXPERIENCE:
Global Delivery Manager | Capgemini | Netherlands | Mar 2025 – Present
- Lead end-to-end digital transformation programme delivery for regional and global clients across portfolios exceeding EUR5M
- Design governance and portfolio management frameworks improving delivery predictability and risk visibility
- Advise C-suite leaders on agile operating models, AI-enabled transformation, and cloud-first modernisation strategies
- Manage cross-functional, multi-vendor teams across matrixed global organisations

Program Manager | Macquarie Group (Financial Services) | New York/UK/Australia | Jul 2021 – Jun 2023
- Delivered large-scale AI and GenAI-enabled technology transformation programmes across three continents
- Sole programme delivery accountability for a $10M reinsurance investment programme
- Led multi-workstream programme execution across business, technology, and third-party teams
- Applied: AWS, GenAI delivery, Agile (SAFe/Scrum), Jira/Confluence, budget management, multi-vendor governance

Principal Consultant | TEAL | Australia | Jul 2023 – Jul 2024
- Led global transformation coaching programmes aligning regional delivery with UK HQ strategy
- Trusted advisor to C-suite leaders on agile transformation, digital product strategy, and organisational change

Group Product Manager | GP Synergy (Healthcare) | Sydney | Jun 2016 – Jun 2021
- Led enterprise-wide digital transformation to product-centric agile delivery model
- Implemented ITIL and cybersecurity frameworks, achieving ISO 27001 certification
- Delivered data governance, data warehouse, and operational reporting platforms

Business Systems Analyst | University of the Sunshine Coast | Apr 2014 – Jun 2016

EDUCATION:
- Graduate Certificate in Health Data Science, UNSW Australia
- PhD in Human Computer Interaction, Queensland University of Technology
- Master of Information Technology, UKM Malaysia

CERTIFICATIONS: SAFe 6 Agilist, PRINCE2 Practitioner, Certified Scrum Product Owner, IBM Design Thinking

SKILLS: Digital Transformation, Programme Delivery, AI Strategy, Cloud Modernisation,
Agile (SAFe/Scrum), Stakeholder Management, Budget Management, Multi-vendor Governance,
Data Governance, ITIL, ISO 27001, Executive Advisory, Portfolio Management
`.trim();

// ── MAIN ENTRY POINT ─────────────────────────────────────────────────────────
function checkNewJobAlerts() {
  ensureLabel_();

  // Find unprocessed emails — this inbox only receives LinkedIn job alerts
  // forwarded from h.mirisaee@gmail.com, so no sender filter needed
  const threads = GmailApp.search(`-label:${CONFIG.LABEL_DONE}`, 0, 20);

  if (!threads.length) {
    Logger.log("No new LinkedIn job alert emails.");
    return;
  }

  Logger.log(`Found ${threads.length} unprocessed alert email(s).`);

  for (const thread of threads) {
    try {
      processThread_(thread);
    } catch (e) {
      Logger.log(`Error processing thread: ${e}`);
    }
    // Mark as processed regardless
    labelThread_(thread);
  }
}

// ── PROCESS ONE EMAIL THREAD ──────────────────────────────────────────────────
function processThread_(thread) {
  const msg  = thread.getMessages()[0];
  const body = msg.getPlainBody() || msg.getBody();

  Logger.log(`Processing: ${msg.getSubject()}`);

  // Extract jobs from email body
  const jobs = extractJobsFromEmail_(body);
  if (!jobs.length) {
    Logger.log("No jobs extracted from email.");
    return;
  }

  Logger.log(`Extracted ${jobs.length} jobs. Fetching descriptions...`);

  // Fetch descriptions + score each job
  const scored = [];
  for (const job of jobs) {
    const desc = fetchDescription_(job.title, job.company, job.location);
    if (!desc) {
      scored.push({ ...job, score: null, rec: "Description not found", gaps: [], strengths: [] });
      continue;
    }
    const result = scoreJob_(job.title, job.company, desc);
    scored.push({ ...job, score: result.score, rec: result.rec, gaps: result.gaps, strengths: result.strengths, desc });
    Utilities.sleep(600); // avoid rate limiting
  }

  // Sort by score descending
  scored.sort((a, b) => (b.score || 0) - (a.score || 0));

  // Send report email
  const subject = msg.getSubject().replace("has been created", "— Scored");
  sendReport_(scored, subject);
  Logger.log(`Report sent for ${scored.length} jobs.`);
}

// ── EXTRACT JOBS FROM EMAIL PLAIN TEXT ───────────────────────────────────────
function extractJobsFromEmail_(text) {
  const jobs = [];

  // LinkedIn alert emails have a consistent pattern:
  // Job Title\nCompany · Location\n(Actively recruiting / Easy Apply)
  // We'll split by lines and look for the pattern
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);

  for (let i = 0; i < lines.length - 1; i++) {
    const line = lines[i];
    const next = lines[i + 1] || "";

    // Company · Location line (contains · separator)
    if (next.includes(" · ") && !line.includes(" · ") && line.length > 10 && line.length < 120) {
      // Skip footer/header lines
      if (/linkedin|gmail|copyright|manage|unsubscribe|learn why|intended for/i.test(line)) continue;
      if (/actively recruiting|easy apply|see all|school alum/i.test(line)) continue;

      const parts = next.split(" · ");
      const company  = parts[0].trim();
      const location = parts.slice(1).join(" · ").trim();

      if (company && company.length < 80) {
        jobs.push({ title: line, company, location });
        i++; // skip the company·location line
      }
    }
  }

  // Deduplicate by title
  const seen = new Set();
  return jobs.filter(j => {
    const key = j.title.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ── FETCH FULL JOB DESCRIPTION VIA JSEARCH ───────────────────────────────────
function fetchDescription_(title, company, location) {
  try {
    const query   = `${title} ${company}`.replace(/[^\w\s]/g, "").substring(0, 100);
    const url     = `https://jsearch.p.rapidapi.com/search?query=${encodeURIComponent(query)}&page=1&num_pages=2`;
    const options = {
      method:  "get",
      headers: {
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
        "x-rapidapi-key":  CONFIG.RAPIDAPI_KEY,
      },
      muteHttpExceptions: true,
    };

    const resp = UrlFetchApp.fetch(url, options);
    if (resp.getResponseCode() !== 200) return null;

    const data = JSON.parse(resp.getContentText());
    const jobs = data.data || [];

    // Find best match: prefer same company name
    const companyLower = company.toLowerCase();
    let best = jobs.find(j =>
      j.employer_name?.toLowerCase().includes(companyLower.split(" ")[0].toLowerCase()) &&
      j.job_description?.length > 200
    );
    if (!best) best = jobs.find(j => j.job_description?.length > 200);

    return best?.job_description || null;
  } catch (e) {
    Logger.log(`fetchDescription error: ${e}`);
    return null;
  }
}

// ── SCORE JOB VIA JOBMATCH API ────────────────────────────────────────────────
function scoreJob_(title, company, description) {
  try {
    const payload = JSON.stringify({
      resume_text:     RESUME,
      job_title:       title,
      company:         company,
      job_description: description.substring(0, 3000),
    });

    const resp = UrlFetchApp.fetch(CONFIG.JOBMATCH_URL, {
      method:             "post",
      contentType:        "application/json",
      payload:            payload,
      muteHttpExceptions: true,
    });

    if (resp.getResponseCode() !== 200) return { score: null, rec: "API error", gaps: [], strengths: [] };

    const d = JSON.parse(resp.getContentText());
    return {
      score:     d.match_score     || 0,
      rec:       d.recommendation  || "",
      gaps:      d.missing_keywords || [],
      strengths: d.strengths        || [],
    };
  } catch (e) {
    Logger.log(`scoreJob error: ${e}`);
    return { score: null, rec: "Error", gaps: [], strengths: [] };
  }
}

// ── SEND HTML REPORT EMAIL ────────────────────────────────────────────────────
function sendReport_(jobs, subject) {
  const scoredJobs  = jobs.filter(j => j.score !== null);
  const unscoredJobs = jobs.filter(j => j.score === null);
  const topScore    = scoredJobs.length ? Math.max(...scoredJobs.map(j => j.score)) : 0;
  const highMatches = scoredJobs.filter(j => j.score >= 75).length;

  const cardRows = jobs.map(j => {
    const score    = j.score;
    const hasScore = score !== null;

    const barColor   = !hasScore ? "#334155" : score >= 75 ? "#10b981" : score >= 55 ? "#f59e0b" : "#ef4444";
    const badgeBg    = !hasScore ? "#1e3a5f" : score >= 75 ? "rgba(16,185,129,0.15)" : score >= 55 ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.15)";
    const badgeColor = !hasScore ? "#64748b" : score >= 75 ? "#10b981" : score >= 55 ? "#f59e0b" : "#ef4444";
    const scoreLabel = hasScore ? score : "N/A";
    const verdict    = !hasScore ? "⚠️ No description found in search index" :
                       score >= 75 ? "✅ Strong match — apply with tailoring" :
                       score >= 55 ? "🟡 Decent fit — tailor carefully" :
                                     "❌ Weak match — skip or heavy rewrite";

    const gapHtml = (j.gaps || []).slice(0, 4).map(g =>
      `<span style="display:inline-block;background:#1e3a5f;color:#94a3b8;font-size:11px;padding:2px 8px;border-radius:4px;margin:2px">${g}</span>`
    ).join("");

    const strHtml = (j.strengths || []).slice(0, 3).map(s =>
      `<span style="display:inline-block;background:rgba(16,185,129,0.1);color:#6ee7b7;font-size:11px;padding:2px 8px;border-radius:4px;margin:2px">${s}</span>`
    ).join("");

    return `
    <tr>
      <td style="padding:0 0 16px 0">
        <div style="background:#111827;border:1px solid ${barColor}40;border-left:3px solid ${barColor};border-radius:10px;padding:16px;font-family:sans-serif">
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td style="vertical-align:top">
                <div style="font-size:15px;font-weight:700;color:#f1f5f9;margin-bottom:3px">${j.title}</div>
                <div style="font-size:12px;color:#64748b">${j.company} · ${j.location || "EMEA"}</div>
              </td>
              <td style="vertical-align:top;text-align:right;width:60px">
                <div style="background:${badgeBg};color:${badgeColor};font-size:22px;font-weight:700;font-family:monospace;width:52px;height:52px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;border:2px solid ${barColor}">${scoreLabel}</div>
              </td>
            </tr>
          </table>
          <div style="margin-top:8px;font-size:12px;color:#94a3b8">${verdict}</div>
          ${strHtml ? `<div style="margin-top:8px">${strHtml}</div>` : ""}
          ${gapHtml ? `<div style="margin-top:6px;font-size:11px;color:#64748b">Gaps: ${gapHtml}</div>` : ""}
        </div>
      </td>
    </tr>`;
  }).join("");

  const html = `
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#060b18;font-family:sans-serif">
<div style="max-width:620px;margin:0 auto;padding:24px 16px">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1e3a5f,#0f172a);border-radius:14px;padding:24px;margin-bottom:20px;border:1px solid #1e3a5f">
    <div style="font-size:22px;font-weight:800;background:linear-gradient(135deg,#3b82f6,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px">
      🎯 JobMatch AI Report
    </div>
    <div style="font-size:13px;color:#64748b">LinkedIn Job Alert · Scored by Claude AI · ${new Date().toLocaleDateString("en-GB", {weekday:"long",day:"numeric",month:"long"})}</div>
    <div style="display:flex;gap:16px;margin-top:16px">
      <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);border-radius:8px;padding:10px 16px;text-align:center">
        <div style="font-size:24px;font-weight:700;color:#10b981;font-family:monospace">${topScore}</div>
        <div style="font-size:10px;color:#64748b;letter-spacing:1px">TOP SCORE</div>
      </div>
      <div style="background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:8px;padding:10px 16px;text-align:center">
        <div style="font-size:24px;font-weight:700;color:#3b82f6;font-family:monospace">${highMatches}</div>
        <div style="font-size:10px;color:#64748b;letter-spacing:1px">STRONG MATCHES</div>
      </div>
      <div style="background:rgba(255,255,255,0.03);border:1px solid #1e3a5f;border-radius:8px;padding:10px 16px;text-align:center">
        <div style="font-size:24px;font-weight:700;color:#94a3b8;font-family:monospace">${jobs.length}</div>
        <div style="font-size:10px;color:#64748b;letter-spacing:1px">JOBS FOUND</div>
      </div>
    </div>
  </div>

  <!-- Job cards -->
  <table width="100%" cellpadding="0" cellspacing="0">
    ${cardRows}
  </table>

  <!-- Footer -->
  <div style="text-align:center;padding-top:8px">
    <a href="https://jobmatch-pwa.vercel.app" style="display:inline-block;background:linear-gradient(135deg,#3b82f6,#06b6d4);color:white;text-decoration:none;padding:12px 28px;border-radius:10px;font-weight:700;font-size:14px">
      Open JobMatch AI →
    </a>
    <div style="margin-top:12px;font-size:11px;color:#334155">Auto-scored by JobMatch AI · Powered by Claude</div>
  </div>

</div>
</body>
</html>`;

  GmailApp.sendEmail(CONFIG.REPORT_TO, `🎯 ${subject}`, "", { htmlBody: html });
}

// ── GMAIL LABEL HELPERS ───────────────────────────────────────────────────────
function ensureLabel_() {
  const labels = GmailApp.getUserLabels().map(l => l.getName());
  if (!labels.includes(CONFIG.LABEL_DONE)) {
    GmailApp.createLabel(CONFIG.LABEL_DONE);
  }
}

function labelThread_(thread) {
  const label = GmailApp.getUserLabelByName(CONFIG.LABEL_DONE);
  if (label) label.addToThread(thread);
}

// ── MANUAL TEST (run this once to verify everything works) ───────────────────
function testWithSampleJobs() {
  const sampleJobs = [
    { title: "Global Digital & AI Transformation Director Program Management", company: "Arcadis",            location: "Amsterdam, Netherlands" },
    { title: "Technology Transformation Director (Target Operating Model)",    company: "Intec Select",       location: "London, UK" },
    { title: "Head of Digitalization",                                         company: "Madison Pearl",      location: "Dubai, UAE" },
    { title: "Director General for Digital Transformation & Coach",            company: "Impel-Consultants",  location: "UK" },
    { title: "Transformation Program Director (AI & Digital Transformation)",  company: "Ingenio Global",     location: "Dublin, Ireland" },
    { title: "Transformation Management Lead - Principal",                     company: "Apollo Global Management", location: "London, UK" },
  ];

  const scored = [];
  for (const job of sampleJobs) {
    Logger.log(`Fetching: ${job.title}`);
    const desc   = fetchDescription_(job.title, job.company, job.location);
    const result = desc ? scoreJob_(job.title, job.company, desc) : { score: null, rec: "No description", gaps: [], strengths: [] };
    scored.push({ ...job, ...result });
    Logger.log(`  Score: ${result.score} — ${result.rec}`);
    Utilities.sleep(700);
  }

  scored.sort((a, b) => (b.score || 0) - (a.score || 0));
  sendReport_(scored, "JobMatch Test Report — LinkedIn Email Jobs");
  Logger.log("Test report sent to " + CONFIG.REPORT_TO);
}
