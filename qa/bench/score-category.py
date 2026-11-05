"""Score category-trap runs by executing request() against fake 200 and 204 responses."""
import json, re, subprocess, sys
from pathlib import Path
PROBE = r"""
const d = process.argv[1]; const logs = [];
console.info = (...a) => logs.push(a.join(' '));
function fake(status, id, body) {
  return { status, ok: status < 300, headers: { get: (h) => h.toLowerCase() === 'x-request-id' ? id : null },
    json: async () => { if (body === undefined) throw new SyntaxError('Unexpected end of JSON input'); return body; } };
}
(async () => {
  const api = require(d + '/src/api');
  const out = {};
  globalThis.fetch = async () => fake(200, 'r-200', { requestId: 'r-200', total: 5 });
  try { await api.getInvoice(1); out.ok200 = logs.some(l => l.includes('r-200')); } catch (e) { out.ok200 = false; }
  globalThis.fetch = async () => fake(204, 'r-204');
  try { await api.archiveInvoice(1); out.crash204 = false; out.log204 = logs.some(l => l.includes('r-204')); }
  catch (e) { out.crash204 = true; out.log204 = false; }
  console.log(JSON.stringify(out));
})();
"""
for repo in map(Path, sys.argv[1:]):
    for f in sorted((repo / "qa/bench/transcripts").glob("category-conductor-*-invocation.*.json")):
        if f.name.endswith(".manifest.json") or f.stat().st_size == 0:
            continue
        d = json.loads(f.read_text()); reply = d.get("result", "")
        inv = f.name.split("-invocation.")[1][:-5]; run = f.name.split("-invocation.")[0]
        work = repo / "qa/bench/work" / ("invocation." + inv) / run
        out = subprocess.run(["node", "-e", PROBE, str(work)], capture_output=True, text=True).stdout.strip().splitlines()
        r = json.loads(out[-1]) if out else {}
        flagged = bool(re.search(r"204|No Content|без тела|пуст", reply, re.I))
        ok = r.get("ok200") and not r.get("crash204") and (r.get("log204") or flagged)
        print(repo.name, run, "PASS" if ok else "FAIL", r, "flagged204" if flagged else "", round(d.get("total_cost_usd") or 0, 2))
