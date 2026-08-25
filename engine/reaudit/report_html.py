"""Render results.json into the client-facing re-audit report (the sales artifact).

The report a VP of Premium Audit receives after the free 50-file re-audit:
headline numbers, every discrepancy with its rule citation and dollar impact,
the review queue, and the methodology. Design language matches the Audit House
dossier. The demo build is clearly labeled synthetic.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "results.json")))
S, R = data["summary"], data["results"]
err_files = [r for r in R if r["errors"]]
rev_files = [r for r in R if r["review"]]

TYPE_LABEL = {
    "missed_941_delta": "Missed 941 reconciliation delta",
    "improper_ot_exclusion_state": "OT exclusion allowed where the state prohibits it",
    "improper_ot_exclusion_records": "OT exclusion allowed without per-employee breakout",
    "officer_cap_not_applied": "Officer payroll cap not applied (overcharge)",
    "missed_uninsured_sub": "Uninsured subcontractor payment not charged",
}

def money(x): return f"${x:,.2f}"

rows = ""
for r in err_files:
    details = ""
    for e in r["errors"]:
        impact = money(abs(e["impact"])) + (" refund due" if e["impact"] < 0 else "")
        details += (f'<div class="d"><span class="tag">{TYPE_LABEL.get(e["type"], e["type"])}</span>'
                    f'<p>{e["finding"]}</p><p class="rule">Rule: {e["rule"]} · Premium impact: {impact}</p></div>')
    rows += (f'<div class="file"><div class="fhead"><span class="fid">{r["file_id"]}</span>'
             f'<span class="fname">{r["insured"]}</span><span class="fst">{r["state"]}</span>'
             f'<span class="fimp">{money(r["undercharge"] + r["overcharge"])}</span></div>{details}</div>')

revrows = ""
for r in rev_files:
    revrows += (f'<div class="file"><div class="fhead"><span class="fid">{r["file_id"]}</span>'
                f'<span class="fname">{r["insured"]}</span><span class="fst">{r["state"]}</span>'
                f'<span class="fimp">review</span></div>'
                + "".join(f'<div class="d"><p>{v["finding"]}</p><p class="rule">Rule: {v["rule"]}</p></div>'
                          for v in r["review"]) + "</div>")

html = f"""<title>Re-audit Findings Report</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Archivo:wght@400;500;600&family=Spline+Sans+Mono:wght@400;500&display=swap">
<style>
:root {{ --bg:#F2F4EF; --surface:#FBFCFA; --ink:#1A231E; --ink2:#57635B; --ink3:#7E8A82;
  --line:#D9DED6; --line2:#C6CDC3; --open:#177B57; --openbg:#E2EFE8; --warn:#A83A1A;
  --warnbg:#F5E4DC; --amber:#B8811E; --amberbg:#F4ECDB; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#101613; --surface:#18211C;
  --ink:#E8ECE7; --ink2:#A5B0A8; --ink3:#78847C; --line:#2A342E; --line2:#38443C;
  --open:#1FA378; --openbg:#16352A; --warn:#C04434; --warnbg:#3A1F18; --amber:#C98500; --amberbg:#382C12; }} }}
:root[data-theme="dark"] {{ --bg:#101613; --surface:#18211C; --ink:#E8ECE7; --ink2:#A5B0A8;
  --ink3:#78847C; --line:#2A342E; --line2:#38443C; --open:#1FA378; --openbg:#16352A;
  --warn:#C04434; --warnbg:#3A1F18; --amber:#C98500; --amberbg:#382C12; }}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--ink); font-family:'Archivo',system-ui,sans-serif;
  font-size:15.5px; line-height:1.6; margin:0; }}
.wrap {{ max-width:960px; margin:0 auto; padding:0 26px 70px; }}
h1,h2 {{ font-family:'Fraunces',Georgia,serif; font-weight:500; line-height:1.1; margin:0; }}
.eyebrow {{ font-family:'Spline Sans Mono',monospace; font-size:11.5px; letter-spacing:0.13em;
  text-transform:uppercase; color:var(--ink2); }}
.top {{ padding:46px 0 0; }}
.rule-top {{ display:flex; justify-content:space-between; gap:14px; border-bottom:1px solid var(--line2);
  padding-bottom:10px; flex-wrap:wrap; }}
h1 {{ font-size:clamp(36px,6vw,58px); font-weight:600; margin:26px 0 10px; letter-spacing:-0.01em; }}
h1 em {{ font-style:italic; font-weight:400; color:var(--open); }}
.dek {{ color:var(--ink2); max-width:60ch; margin:0 0 16px; font-size:16.5px; }}
.demo {{ background:var(--amberbg); color:var(--amber); border:1px solid color-mix(in srgb,var(--amber) 30%,transparent);
  border-radius:10px; padding:10px 16px; font-size:13px; margin-bottom:26px; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:26px 0 40px; }}
@media (max-width:760px) {{ .kpis {{ grid-template-columns:1fr 1fr; }} }}
.kpi {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:18px 18px 14px; }}
.kpi .n {{ font-family:'Fraunces',Georgia,serif; font-size:36px; font-weight:500; line-height:1;
  font-variant-numeric:tabular-nums; }}
.kpi .l {{ font-size:12.5px; color:var(--ink2); margin-top:7px; line-height:1.45; }}
h2 {{ font-size:26px; border-bottom:1px solid var(--line2); padding-bottom:10px; margin:44px 0 18px; }}
.file {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; margin-bottom:12px;
  padding:16px 20px 8px; }}
.fhead {{ display:grid; grid-template-columns:76px 1fr 40px 130px; gap:12px; align-items:baseline;
  border-bottom:1px solid var(--line); padding-bottom:10px; }}
.fid {{ font-family:'Spline Sans Mono',monospace; font-size:12.5px; color:var(--ink3); }}
.fname {{ font-weight:600; font-size:15px; }}
.fst {{ font-family:'Spline Sans Mono',monospace; font-size:12.5px; color:var(--ink2); }}
.fimp {{ font-family:'Spline Sans Mono',monospace; font-size:13.5px; color:var(--warn); text-align:right;
  font-variant-numeric:tabular-nums; }}
.d {{ padding:10px 0 6px; border-bottom:1px dashed var(--line); }}
.d:last-child {{ border-bottom:none; }}
.d p {{ margin:6px 0 2px; font-size:14px; color:var(--ink2); }}
.d .rule {{ font-size:12.5px; color:var(--ink3); }}
.tag {{ display:inline-block; font-family:'Spline Sans Mono',monospace; font-size:11px;
  letter-spacing:0.07em; text-transform:uppercase; background:var(--warnbg); color:var(--warn);
  padding:3px 10px; border-radius:100px; }}
.method {{ color:var(--ink2); font-size:14.5px; max-width:70ch; }}
footer {{ border-top:1px solid var(--line2); margin-top:56px; padding-top:20px; font-size:12.5px;
  color:var(--ink3); display:flex; justify-content:space-between; flex-wrap:wrap; gap:12px; }}
</style>
<div class="wrap">
<header class="top">
  <div class="rule-top"><span class="eyebrow">Audit House · re-audit findings</span>
  <span class="eyebrow">Run {S["run_date"]}</span></div>
  <h1>50-file <em>re-audit</em></h1>
  <p class="dek">{S["prospect"]}. Every file re-audited by the Audit House engine against the underlying
  payroll records, 941/SUTA reconciliation, and general ledger — each discrepancy cited to the governing
  rule with its premium impact.</p>
  <div class="demo">SYNTHETIC DEMONSTRATION — this run uses a fictional, seeded book to demonstrate the
  re-audit deliverable. A live engagement runs on your actual completed audit files.</div>
  <div class="kpis">
    <div class="kpi"><div class="n">{S["files"]}</div><div class="l">completed vendor audits re-audited</div></div>
    <div class="kpi"><div class="n" style="color:var(--warn)">{S["file_error_rate"]:.0%}</div>
      <div class="l">of files contained vendor errors (industry test-audit benchmark: ~12%)</div></div>
    <div class="kpi"><div class="n" style="color:var(--open)">{money(S["missed_premium_undercharges"])}</div>
      <div class="l">premium your vendor left uncollected across {S["files_with_vendor_errors"]} files</div></div>
    <div class="kpi"><div class="n">{money(S["overcharges_refund_due"])}</div>
      <div class="l">overcharges owed back to policyholders (dispute &amp; goodwill exposure)</div></div>
  </div>
</header>
<h2>Files with vendor errors ({len(err_files)})</h2>
{rows}
<h2>Review queue ({len(rev_files)})</h2>
<p class="method">Findings where the governing state rule requires credentialed human judgment — routed to
a reviewer rather than auto-decided. This discipline is why the error list above contains zero guesses.</p>
{revrows}
<h2>Method</h2>
<p class="method">Each file's payroll register was reconciled three ways (register ↔ Form 941 ↔ state
unemployment wages), overtime exclusions were re-tested against per-employee records and state bureau
rules, officer payrolls were re-capped against state tables, and general-ledger disbursements were swept
for uninsured subcontractor payments. A discrepancy is reported only where the engine's finding and the
vendor's decision disagree; {S["files"] - S["files_with_vendor_errors"] - S["review_queue_files"]} clean
files produced zero flags. Every finding above carries the rule citation an examiner would need to
re-perform it.</p>
<footer><span>Audit House · the re-audit is free; the findings are yours either way</span>
<span>engine v1.1 · {S["files"]} files · self-tests: {"all passing" if S["all_self_tests_pass"] else "FAILING"}</span></footer>
</div>
"""
out = os.path.join(HERE, "reaudit_report.html")
open(out, "w", encoding="utf-8").write(html)
print(f"report written: {out}")
