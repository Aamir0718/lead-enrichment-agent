"""Report generator (deterministic, no LLM).

Reads output.json and renders report.html: a light, premium results
showcase for the pipeline's extracted company intelligence. Safe to re-run
any time after main.py -- it always reflects the current output.json.

Usage:
    python generate_report.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_PATH = Path(__file__).parent / "output.json"
REPORT_PATH = Path(__file__).parent / "report.html"

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Lead Enrichment Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css">
<style>
  /* Design tokens -- light theme only, by explicit request. No dark-mode branch. */
  :root{
    --bg:#FAFAFA;
    --surface:#FFFFFF;
    --surface-sunken:#F3F4F6;
    --border:#E5E5E9;
    --border-soft:#EEEEF1;
    --text-primary:#16181D;
    --text-secondary:#5B5F6B;
    --text-tertiary:#9A9DA6;
    --accent:#2952E3;
    --accent-soft:#EEF1FD;
    --success:#1E8E5A;
    --success-soft:#E9F7EF;
    --warning:#B7791F;
    --warning-soft:#FBF3E6;
    --danger:#C23B3B;
    --danger-soft:#FBEAEA;
    --radius-lg:20px;
    --radius-md:12px;
    --radius-sm:10px;
    --font-sans:'Geist',ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
    --font-mono:'Geist Mono',ui-monospace,'SF Mono','Cascadia Code','Roboto Mono',monospace;
  }

  *,*::before,*::after{ box-sizing:border-box; }
  html{ color-scheme:light; }
  body{
    margin:0;
    background:var(--bg);
    color:var(--text-primary);
    font-family:var(--font-sans);
    font-size:16px;
    line-height:1.5;
    -webkit-font-smoothing:antialiased;
  }
  img{ max-width:100%; }
  a{ color:inherit; text-decoration:none; }
  ul{ margin:0; padding:0; list-style:none; }
  p{ margin:0; }

  .wrap{ max-width:1100px; margin:0 auto; padding-inline:24px; }

  /* Header */
  .site-header{ border-bottom:1px solid var(--border-soft); padding-block:20px; }
  .header-inner{ display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; }
  .brand{ display:flex; align-items:center; gap:12px; }
  .brand-mark{
    display:flex; align-items:center; justify-content:center;
    width:38px; height:38px; border-radius:var(--radius-sm);
    background:var(--accent); color:#fff; font-family:var(--font-mono);
    font-size:13px; font-weight:600; letter-spacing:0.02em;
  }
  .brand-text{ display:flex; flex-direction:column; line-height:1.25; }
  .brand-name{ font-weight:600; font-size:15px; }
  .brand-sub{ font-size:13px; color:var(--text-tertiary); }
  .repo-link{
    display:inline-flex; align-items:center; gap:8px;
    background:var(--accent); color:#fff; font-size:14px; font-weight:500;
    padding:9px 16px; border-radius:999px; transition:transform .15s ease, opacity .15s ease;
  }
  .repo-link:hover{ opacity:0.9; }
  .repo-link:active{ transform:scale(0.98); }
  .repo-link i{ font-size:16px; }

  /* Intro */
  .intro{ padding-block:48px 32px; max-width:640px; }
  .intro h1{ font-size:clamp(28px,4vw,38px); font-weight:600; letter-spacing:-0.02em; margin:0 0 12px; }
  .intro-sub{ color:var(--text-secondary); font-size:16px; line-height:1.6; }
  .intro-sub span{ color:var(--text-primary); font-weight:500; }

  /* Stats */
  .stats{
    display:grid; grid-template-columns:repeat(4,1fr);
    border-top:1px solid var(--border-soft); border-bottom:1px solid var(--border-soft);
    padding-block:28px; margin-bottom:56px;
  }
  .stat{ display:flex; flex-direction:column; gap:6px; padding-inline:20px; border-left:1px solid var(--border-soft); }
  .stat:first-child{ border-left:none; padding-left:0; }
  .stat-value{ font-family:var(--font-mono); font-size:28px; font-weight:600; letter-spacing:-0.01em; }
  .stat-label{ font-size:13px; color:var(--text-tertiary); }

  /* Cards */
  .cards{ display:flex; flex-direction:column; gap:20px; padding-bottom:64px; }
  .card{
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius-lg); padding:28px;
    opacity:0; transform:translateY(16px);
    transition:opacity .5s cubic-bezier(.16,1,.3,1), transform .5s cubic-bezier(.16,1,.3,1);
  }
  .card.is-visible{ opacity:1; transform:translateY(0); }

  .card-head{ display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:20px; }
  .card-head-left{ display:flex; flex-direction:column; gap:8px; }
  .domain{ font-family:var(--font-mono); font-size:19px; font-weight:600; margin:0; letter-spacing:-0.01em; }
  .status-pill{
    display:inline-flex; align-items:center; gap:6px; width:fit-content;
    font-size:12px; font-weight:500; padding:4px 10px; border-radius:999px;
  }
  .status-pill i{ font-size:13px; }
  .status-success{ background:var(--success-soft); color:var(--success); }
  .status-partial{ background:var(--warning-soft); color:var(--warning); }
  .status-failed{ background:var(--danger-soft); color:var(--danger); }

  .confidence{ text-align:right; flex-shrink:0; }
  .confidence-value{ display:block; font-family:var(--font-mono); font-size:26px; font-weight:600; }
  .confidence-label{ font-size:12px; color:var(--text-tertiary); }

  .error-text{ color:var(--danger); font-size:14px; display:flex; align-items:center; gap:8px; }

  .card-body{ display:grid; grid-template-columns:1.4fr 1fr; gap:32px; }
  .card-main{ display:flex; flex-direction:column; gap:20px; }
  .card-side{ display:flex; flex-direction:column; gap:20px; border-left:1px solid var(--border-soft); padding-left:28px; }

  .overview{ font-size:15.5px; line-height:1.65; color:var(--text-primary); }

  .field{ display:flex; flex-direction:column; gap:8px; }
  .field-label{ font-size:11.5px; font-weight:600; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-tertiary); }
  .field-value{ font-size:14.5px; color:var(--text-secondary); line-height:1.55; }

  .chip-row{ display:flex; flex-wrap:wrap; gap:8px; }
  .chip{
    display:inline-flex; align-items:center; gap:6px;
    background:var(--accent-soft); color:var(--accent);
    font-size:13px; font-weight:500; padding:6px 12px; border-radius:999px;
    transition:transform .15s ease;
  }
  .chip:hover{ transform:translateY(-1px); }
  .chip i{ font-size:14px; }

  .empty-note{ font-size:13.5px; color:var(--text-tertiary); font-style:normal; }

  .leadership-list{ display:flex; flex-direction:column; gap:12px; }
  .leadership-list li{ display:flex; align-items:center; gap:10px; }
  .avatar{
    display:flex; align-items:center; justify-content:center; flex-shrink:0;
    width:32px; height:32px; border-radius:50%;
    background:var(--accent-soft); color:var(--accent);
    font-family:var(--font-mono); font-size:12px; font-weight:600;
  }
  .person{ display:flex; flex-direction:column; line-height:1.3; flex:1; min-width:0; }
  .person-name{ font-size:14px; font-weight:500; }
  .person-role{ font-size:12.5px; color:var(--text-tertiary); }
  .icon-link{ color:var(--text-tertiary); flex-shrink:0; transition:color .15s ease; }
  .icon-link:hover{ color:var(--accent); }

  .pages-list{ display:flex; flex-direction:column; gap:6px; }
  .page-link{
    display:flex; align-items:center; gap:6px;
    font-size:13px; color:var(--text-secondary);
    overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
    transition:color .15s ease;
  }
  .page-link:hover{ color:var(--accent); }
  .page-link i{ font-size:13px; color:var(--text-tertiary); flex-shrink:0; }

  .meta-row{ font-size:13px; color:var(--text-tertiary); display:flex; align-items:center; gap:6px; }
  .meta-row i{ font-size:14px; }

  .notes{ margin-top:20px; padding-top:20px; border-top:1px solid var(--border-soft); display:flex; flex-direction:column; gap:8px; }
  .notes-list{ display:flex; flex-direction:column; gap:6px; }
  .notes-list li{ font-size:13.5px; color:var(--text-secondary); padding-left:16px; position:relative; }
  .notes-list li::before{ content:'-'; position:absolute; left:0; color:var(--text-tertiary); }

  /* Footer */
  .site-footer{ border-top:1px solid var(--border-soft); padding-block:28px; }
  .site-footer p{ font-size:13px; color:var(--text-tertiary); max-width:640px; line-height:1.6; }

  @media (prefers-reduced-motion: reduce){
    .card{ transition:none; opacity:1; transform:none; }
  }

  @media (max-width:768px){
    .stats{ grid-template-columns:repeat(2,1fr); row-gap:20px; }
    .stat:nth-child(3){ border-left:none; padding-left:0; }
    .card-body{ grid-template-columns:1fr; }
    .card-side{ border-left:none; padding-left:0; border-top:1px solid var(--border-soft); padding-top:20px; }
    .header-inner{ flex-direction:column; align-items:flex-start; }
  }
</style>
</head>
<body>

<header class="site-header">
  <div class="wrap header-inner">
    <div class="brand">
      <span class="brand-mark">LE</span>
      <div class="brand-text">
        <span class="brand-name">Lead Enrichment Agent</span>
        <span class="brand-sub">Autonomous company intelligence pipeline</span>
      </div>
    </div>
    <a class="repo-link" href="__REPO_URL__" target="_blank" rel="noopener">
      <i class="ph ph-github-logo"></i> View repository
    </a>
  </div>
</header>

<main class="wrap">
  <section class="intro">
    <h1>Extraction results</h1>
    <p class="intro-sub">Structured company intelligence extracted from public web presence across <span>__DOMAIN_COUNT__ target domains</span>, generated __GENERATED_AT__.</p>
  </section>

  <section class="stats" aria-label="Run summary">
    <div class="stat"><span class="stat-value" id="stat-domains">-</span><span class="stat-label">Domains processed</span></div>
    <div class="stat"><span class="stat-value" id="stat-success">-</span><span class="stat-label">Success rate</span></div>
    <div class="stat"><span class="stat-value" id="stat-confidence">-</span><span class="stat-label">Avg. confidence</span></div>
    <div class="stat"><span class="stat-value" id="stat-calls">-</span><span class="stat-label">Total LLM calls</span></div>
  </section>

  <section class="cards" id="cards" aria-label="Per-domain results"></section>
</main>

<footer class="site-footer">
  <div class="wrap">
    <p>Pipeline: Scraper &rarr; Processor &rarr; Extractor &rarr; Critique. The Scraper, Processor and Critique stages run locally with no model calls; only the Extractor stage calls an LLM, once per domain by default.</p>
  </div>
</footer>

<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
(function(){
  const records = JSON.parse(document.getElementById('report-data').textContent);
  const container = document.getElementById('cards');

  function escapeHtml(str){
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
  }

  function initials(name){
    return (name || '').split(' ').filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
  }

  function statusMeta(status){
    if (status === 'success') return { icon: 'ph-check-circle', label: 'Success', cls: 'status-success' };
    if (status === 'partial') return { icon: 'ph-warning-circle', label: 'Partial', cls: 'status-partial' };
    return { icon: 'ph-x-circle', label: 'Failed', cls: 'status-failed' };
  }

  function bareUrl(u){
    return (u || '').replace(/^https?:\\/\\//, '').replace(/\\/$/, '');
  }

  function cardHtml(r, index){
    const sm = statusMeta(r.status);
    const confidence = (typeof r.confidence_score === 'number') ? r.confidence_score.toFixed(2) : '-';

    const bodyHtml = (r.status === 'failed')
      ? `<p class="error-text"><i class="ph ph-warning-circle"></i>${escapeHtml(r.error || 'No data could be extracted for this domain.')}</p>`
      : `
      <div class="card-body">
        <div class="card-main">
          <p class="overview">${escapeHtml(r.company_overview || 'No overview extracted.')}</p>
          <div class="field">
            <span class="field-label">Target audience</span>
            <p class="field-value">${escapeHtml(r.target_audience || 'Not identified.')}</p>
          </div>
          <div class="field">
            <span class="field-label">Contact emails</span>
            <div class="chip-row">
              ${(r.contact_emails && r.contact_emails.length)
                ? r.contact_emails.map(e => `<a class="chip" href="mailto:${escapeHtml(e)}"><i class="ph ph-envelope-simple"></i>${escapeHtml(e)}</a>`).join('')
                : '<span class="empty-note">None found on public pages</span>'}
            </div>
          </div>
        </div>

        <div class="card-side">
          <div class="field">
            <span class="field-label">Leadership</span>
            ${(r.leadership && r.leadership.length) ? `
              <ul class="leadership-list">
                ${r.leadership.map(m => `
                  <li>
                    <span class="avatar">${escapeHtml(initials(m.name))}</span>
                    <span class="person">
                      <span class="person-name">${escapeHtml(m.name)}</span>
                      ${m.role ? `<span class="person-role">${escapeHtml(m.role)}</span>` : ''}
                    </span>
                    ${m.linkedin_url ? `<a class="icon-link" href="${escapeHtml(m.linkedin_url)}" target="_blank" rel="noopener"><i class="ph ph-linkedin-logo"></i></a>` : ''}
                  </li>
                `).join('')}
              </ul>
            ` : '<p class="empty-note">None identified from scraped pages</p>'}
          </div>

          <div class="field">
            <span class="field-label">Pages scraped</span>
            <div class="pages-list">
              ${(r.pages_scraped || []).map(u => `<a class="page-link" href="${escapeHtml(u)}" target="_blank" rel="noopener"><i class="ph ph-arrow-square-out"></i>${escapeHtml(bareUrl(u))}</a>`).join('')}
            </div>
          </div>

          <div class="meta-row"><i class="ph ph-lightning"></i>${r.llm_calls_used ?? 0} LLM call${(r.llm_calls_used === 1) ? '' : 's'}</div>
        </div>
      </div>

      ${(r.critique_notes && r.critique_notes.length) ? `
        <div class="notes">
          <span class="field-label">Critique notes</span>
          <ul class="notes-list">
            ${r.critique_notes.map(n => `<li>${escapeHtml(n)}</li>`).join('')}
          </ul>
        </div>
      ` : ''}
      `;

    return `
      <article class="card reveal" style="transition-delay:${index * 60}ms">
        <div class="card-head">
          <div class="card-head-left">
            <span class="status-pill ${sm.cls}"><i class="ph ${sm.icon}"></i>${sm.label}</span>
            <h2 class="domain">${escapeHtml(r.domain)}</h2>
          </div>
          ${r.status !== 'failed' ? `
            <div class="confidence">
              <span class="confidence-value">${confidence}</span>
              <span class="confidence-label">confidence</span>
            </div>
          ` : ''}
        </div>
        ${bodyHtml}
      </article>
    `;
  }

  container.innerHTML = records.map(cardHtml).join('');

  const total = records.length;
  const succeeded = records.filter(r => r.status === 'success').length;
  const scored = records.filter(r => typeof r.confidence_score === 'number');
  const avgConfidence = scored.length ? (scored.reduce((a, r) => a + r.confidence_score, 0) / scored.length) : 0;
  const totalCalls = records.reduce((a, r) => a + (r.llm_calls_used || 0), 0);

  document.getElementById('stat-domains').textContent = total;
  document.getElementById('stat-success').textContent = total ? Math.round((succeeded / total) * 100) + '%' : '-';
  document.getElementById('stat-confidence').textContent = avgConfidence.toFixed(2);
  document.getElementById('stat-calls').textContent = totalCalls;

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const cards = document.querySelectorAll('.reveal');
  if (!reduceMotion && 'IntersectionObserver' in window){
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting){
          entry.target.classList.add('is-visible');
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    cards.forEach((el) => io.observe(el));
  } else {
    cards.forEach((el) => el.classList.add('is-visible'));
  }
})();
</script>
</body>
</html>
"""


def generate_report(repo_url: str = "https://github.com/Aamir0718/lead-enrichment-agent") -> None:
    if not OUTPUT_PATH.exists():
        raise SystemExit(f"{OUTPUT_PATH} not found -- run `python main.py` first.")

    records = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")

    html = (
        HTML_TEMPLATE
        .replace("__REPO_URL__", repo_url)
        .replace("__DOMAIN_COUNT__", str(len(records)))
        .replace("__GENERATED_AT__", generated_at)
        .replace("__REPORT_DATA__", json.dumps(records))
    )

    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    generate_report()
