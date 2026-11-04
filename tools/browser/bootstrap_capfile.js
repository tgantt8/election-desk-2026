// Installs window.__cap / __capRetry / __save / __capFile on a Clarity tab (paste into the tab's console or run via the browser tool).
// Set window.CLARITY_BASE first on a non-Macomb county tab, e.g. CLARITY_BASE='https://results.enr.clarityelections.com/MI/Oakland/127284'.
window.__cap = async () => {
  const BASE = (typeof CLARITY_BASE !== "undefined") ? CLARITY_BASE : "https://results.enr.clarityelections.com/MI/Macomb/127293";
  const DETAIL_RX = (typeof CLARITY_DETAIL_RX !== "undefined") ? CLARITY_DETAIL_RX : /58th District|State Senator 24th/i;
  // contests kept (county totals); local offices, judges, school boards and village races stay out to keep the capture small
  const CONTEST_RX = (typeof CLARITY_CONTEST_RX !== "undefined") ? CLARITY_CONTEST_RX
    : /^Governor|Secretary of State|Attorney General|United States Senator|Representative in Congress|State Senator|State Representative|Representative in State Legislature|County Executive|Straight Party|^State Proposal/i;
  const fetched = new Date().toISOString();
  const ver = (await fetch(BASE + "/current_ver.txt", { cache: "no-store" }).then(r => r.text())).trim();
  const zipBuf = await fetch(`${BASE}/${ver}/reports/detailxml.zip`, { cache: "no-store" }).then(r => r.arrayBuffer());
  const zsha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", zipBuf))].map(b => b.toString(16).padStart(2, "0")).join("");
  async function unzipFirst(buf) {
    const dv = new DataView(buf);
    if (dv.getUint32(0, true) !== 0x04034b50) throw new Error("not a zip");
    const method = dv.getUint16(8, true), flags = dv.getUint16(6, true);
    let csize = dv.getUint32(18, true);
    const nlen = dv.getUint16(26, true), elen = dv.getUint16(28, true);
    const start = 30 + nlen + elen;
    if ((flags & 8) || csize === 0) { const u8 = new Uint8Array(buf); let i = u8.length - 22;
      while (i > 0 && !(u8[i] === 0x50 && u8[i + 1] === 0x4b && u8[i + 2] === 5 && u8[i + 3] === 6)) i--;
      csize = dv.getUint32(dv.getUint32(i + 16, true) + 20, true); }
    const comp = new Uint8Array(buf, start, csize);
    if (method === 0) return new TextDecoder().decode(comp);
    const ds = new DecompressionStream("deflate-raw"); const w = ds.writable.getWriter(); w.write(comp); w.close();
    return new TextDecoder().decode(await new Response(ds.readable).arrayBuffer());
  }
  const doc = new DOMParser().parseFromString(await unzipFirst(zipBuf), "text/xml");
  const num = v => (v === null || v === undefined || v === "") ? null : Number(v);
  const txt = n => { const e = doc.querySelector(n); return e ? e.textContent : null; };
  const VT = []; doc.querySelectorAll("Contest > Choice > VoteType").forEach(v => { const n = v.getAttribute("name"); if (!VT.includes(n)) VT.push(n); });
  const prAll = {}; doc.querySelectorAll("VoterTurnout > Precincts > Precinct").forEach(p => { prAll[p.getAttribute("name")] = [num(p.getAttribute("totalVoters")), num(p.getAttribute("ballotsCast")), num(p.getAttribute("percentReporting"))]; });
  const pr = {}; const c = [];
  doc.querySelectorAll("ElectionResult > Contest").forEach(ct => {
    const text = ct.getAttribute("text"); if (!CONTEST_RX.test(text)) return; const detail = DETAIL_RX.test(text);
    const choices = []; const pd = {};
    ct.querySelectorAll(":scope > Choice").forEach((ch, ci) => {
      const row = [ch.getAttribute("text"), ch.getAttribute("party"), num(ch.getAttribute("totalVotes"))]; VT.forEach(() => row.push(null));
      ch.querySelectorAll(":scope > VoteType").forEach(vt => {
        const vi = VT.indexOf(vt.getAttribute("name")); row[3 + vi] = num(vt.getAttribute("votes"));
        if (detail) vt.querySelectorAll(":scope > Precinct").forEach(p => { const pn = p.getAttribute("name");
          if (!pd[pn]) pd[pn] = []; if (!pd[pn][ci]) pd[pn][ci] = VT.map(() => null); pd[pn][ci][vi] = num(p.getAttribute("votes")); pr[pn] = prAll[pn] || null; });
      });
      choices.push(row);
    });
    // a precinct that has not reported (no turnout row) and shows only zeros is left out: absent, not zero
    for (const pn of Object.keys(pd)) if (!pr[pn] && pd[pn].every(v => !v || v.every(x => !x))) { delete pd[pn]; delete pr[pn]; }
    const regv = ct.querySelector(":scope > VoteType[name='regVotersCounty']");
    c.push([ct.getAttribute("key"), text, num(ct.getAttribute("precinctsReporting")), num(ct.getAttribute("precinctsReported")), regv ? num(regv.getAttribute("votes")) : null, choices, detail ? pd : null]);
  });
  const t = doc.querySelector("VoterTurnout");
  const obj = { k: "cc1", base: BASE, ver, ts: txt("Timestamp"), zsha, zb: zipBuf.byteLength, fetched, turnout: t ? [num(t.getAttribute("totalVoters")), num(t.getAttribute("ballotsCast"))] : null, vt: VT, c, pr };
  const body = JSON.stringify(obj);
  let crc = -1; for (let i = 0; i < body.length; i++) { crc ^= body.charCodeAt(i); for (let k = 0; k < 8; k++) crc = (crc >>> 1) ^ (0xEDB88320 & -(crc & 1)); }
  obj.crc = (crc ^ -1) >>> 0;
  return JSON.stringify(obj);
};
window.__capRetry = async (n) => { let e; for (let i=0;i<n;i++) { try { return await window.__cap(); } catch (x) { e=x; await new Promise(r=>setTimeout(r,1500)); } } return 'ERR ' + String(e); };
window.__save = (name, txt) => { const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([txt],{type:'application/json'})); a.download=name; document.body.appendChild(a); a.click(); setTimeout(()=>{URL.revokeObjectURL(a.href); a.remove();}, 2000); };
window.__capFile = async (tag) => { const txt = await window.__capRetry(3); if (typeof txt !== 'string' || !txt.startsWith('{')) return 'FAILED ' + String(txt).slice(0,100); const o = JSON.parse(txt); const name = `desk_${tag||'x'}_${o.ver}.json`; window.__save(name, txt); return {name, ver: o.ver, ts: o.ts, bytes: txt.length, contests: o.c.length}; };
'installed'