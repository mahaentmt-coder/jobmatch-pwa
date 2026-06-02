# JobMatch AI — Mobile PWA

AI-powered job matching, CV tailoring and application tracker.
Installable on Android from the browser. Powered by Claude AI.

---

## Deploy to Vercel (5 minutes)

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "JobMatch AI PWA"
git remote add origin https://github.com/YOUR_USERNAME/jobmatch-pwa.git
git push -u origin main
```

### 2. Deploy on Vercel
1. Go to vercel.com → New Project
2. Import your GitHub repo
3. Framework Preset: **Other**
4. Click Deploy

### 3. Add your Anthropic API key
1. Vercel Dashboard → your project → Settings → Environment Variables
2. Add: `ANTHROPIC_API_KEY` = `sk-ant-...`
3. Redeploy

---

## Install on Android

1. Open your Vercel URL in **Chrome**
2. Tap the **⋮ menu** → "Add to Home screen"
3. The app installs like a native app — no Play Store needed

---

## How to use

| Tab | What to do |
|-----|-----------|
| 📄 Resume | Paste your full CV text once — saved locally |
| 🔍 Search | Paste any job description + title + company |
| 🎯 Match | Pick a saved job → get AI match score + gap analysis |
| ✨ Tailor | Pick a job → AI rewrites your summary, bullets + cover letter |
| 📊 Track | Track application status (Applied → Interview → Offer) |

**Quick tip**: On any job card, tap 🎯 Match or ✨ Tailor to jump straight there.

---

## Project structure
```
jobmatcher-pwa/
├── index.html       # Full mobile PWA (single file)
├── manifest.json    # Android install config
├── sw.js            # Service worker (offline support)
├── vercel.json      # Vercel routing config
├── requirements.txt # No external Python deps needed
└── api/
    ├── match.py     # POST /api/match  — AI match scoring
    └── tailor.py    # POST /api/tailor — AI CV tailoring
```

---

## API endpoints

### POST /api/match
```json
{
  "resume_text": "...",
  "job_description": "...",
  "job_title": "Service Delivery Director",
  "company": "Salesforce",
  "job_id": "optional-id"
}
```
Returns: `match_score`, `matched_keywords`, `missing_keywords`, `strengths`, `gaps`, `recommendation`

### POST /api/tailor
```json
{
  "resume_text": "...",
  "job_description": "...",
  "job_title": "...",
  "company": "..."
}
```
Returns: `tailored_summary`, `tailored_bullets`, `keywords_added`, `cover_letter`
