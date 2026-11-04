// Clarity (Scytl) ENR capture — runs INSIDE a real browser tab that has the county's Clarity page open
// (results.enr.clarityelections.com/<ST>/<County>/<electionID>/...). Clarity sits behind an AWS WAF JavaScript
// challenge that refuses plain HTTP clients; a browser that has loaded the public page passes it legitimately, and
// this script reads the same files the page itself reads. Nothing here spoofs or defeats a challenge.
//
// Output: one base64 string of a gzip'd JSON bundle (ver, timestamp, zip sha256, every contest's county totals by
// vote type, plus precinct × choice × vote type for the contests matched by DETAIL_RX). Feed it to
//   python3 tools/ingest_clarity_bundle.py --source-id macomb_clarity_enr --bundle <file>
// which stores it as an append-only snapshot and appends results records.
//
// Usage from the desk operator's browser console (or Claude's browser tool): set BASE, paste, await the result.
(async () => {
  const BASE = (typeof CLARITY_BASE !== "undefined") ? CLARITY_BASE : "https://results.enr.clarityelections.com/MI/Macomb/127293";
  const DETAIL_RX = (typeof CLARITY_DETAIL_RX !== "undefined") ? CLARITY_DETAIL_RX
    : /State Representative|State Senator|Representative in Congress|Governor|United States Senator|Secretary of State|Attorney General|County Executive|Straight Party/i;
  const fetched_at = new Date().toISOString();
  const ver = (await fetch(BASE + "/current_ver.txt", { cache: "no-store" }).then(r => r.text())).trim();
  const zipBuf = await fetch(`${BASE}/${ver}/reports/detailxml.zip`, { cache: "no-store" }).then(r => r.arrayBuffer());
  const zip_sha256 = [...new Uint8Array(await crypto.subtle.digest("SHA-256", zipBuf))].map(b => b.toString(16).padStart(2, "0")).join("");

  async function unzipFirst(buf) {  // single-file zip, stored or deflate
    const dv = new DataView(buf);
    if (dv.getUint32(0, true) !== 0x04034b50) throw new Error("not a zip");
    const method = dv.getUint16(8, true), flags = dv.getUint16(6, true);
    let csize = dv.getUint32(18, true);
    const nlen = dv.getUint16(26, true), elen = dv.getUint16(28, true);
    const start = 30 + nlen + elen;
    if ((flags & 8) || csize === 0) {  // sizes live in the central directory
      const u8 = new Uint8Array(buf); let i = u8.length - 22;
      while (i > 0 && !(u8[i] === 0x50 && u8[i + 1] === 0x4b && u8[i + 2] === 5 && u8[i + 3] === 6)) i--;
      csize = dv.getUint32(dv.getUint32(i + 16, true) + 20, true);
    }
    const comp = new Uint8Array(buf, start, csize);
    if (method === 0) return new TextDecoder().decode(comp);
    const ds = new DecompressionStream("deflate-raw"); const w = ds.writable.getWriter(); w.write(comp); w.close();
    return new TextDecoder().decode(await new Response(ds.readable).arrayBuffer());
  }
  const xml = await unzipFirst(zipBuf);
  const doc = new DOMParser().parseFromString(xml, "text/xml");
  const t = (el, name) => { const n = el.querySelector(name); return n ? n.textContent : null; };
  const num = v => (v === null || v === undefined || v === "") ? null : Number(v);
  const turnoutEl = doc.querySelector("VoterTurnout");
  const precinct_reporting = {};
  doc.querySelectorAll("VoterTurnout > Precincts > Precinct").forEach(p => {
    precinct_reporting[p.getAttribute("name")] = { totalVoters: num(p.getAttribute("totalVoters")), ballotsCast: num(p.getAttribute("ballotsCast")), percentReporting: num(p.getAttribute("percentReporting")) };
  });
  const contests = [];
  doc.querySelectorAll("ElectionResult > Contest").forEach(c => {
    const text = c.getAttribute("text");
    const detail = DETAIL_RX.test(text);
    const choices = [];
    c.querySelectorAll(":scope > Choice").forEach(ch => {
      const by_type = {}, precincts = {};
      ch.querySelectorAll(":scope > VoteType").forEach(vt => {
        const vn = vt.getAttribute("name");
        by_type[vn] = num(vt.getAttribute("votes"));
        if (detail) vt.querySelectorAll(":scope > Precinct").forEach(p => {
          const pn = p.getAttribute("name"); (precincts[pn] = precincts[pn] || {})[vn] = num(p.getAttribute("votes"));
        });
      });
      const row = { key: ch.getAttribute("key"), text: ch.getAttribute("text"), party: ch.getAttribute("party"), totalVotes: num(ch.getAttribute("totalVotes")), by_type };
      if (detail) row.precincts = precincts;
      choices.push(row);
    });
    const regv = c.querySelector(":scope > VoteType[name='regVotersCounty']");
    contests.push({ key: c.getAttribute("key"), text, voteFor: num(c.getAttribute("voteFor")), isQuestion: c.getAttribute("isQuestion") === "true",
      precinctsTotal: num(c.getAttribute("precinctsReporting")), precinctsReported: num(c.getAttribute("precinctsReported")),
      regVoters: regv ? num(regv.getAttribute("votes")) : null, detail, choices });
  });
  const bundle = { kind: "clarity_detailxml_bundle", v: 1, base: BASE, ver, fetched_at, zip_sha256, zip_bytes: zipBuf.byteLength, xml_bytes: xml.length,
    timestamp: t(doc, "Timestamp"), election_name: t(doc, "ElectionName"), election_date: t(doc, "ElectionDate"), region: t(doc, "Region"),
    turnout: turnoutEl ? { totalVoters: num(turnoutEl.getAttribute("totalVoters")), ballotsCast: num(turnoutEl.getAttribute("ballotsCast")), voterTurnout: num(turnoutEl.getAttribute("voterTurnout")) } : null,
    precinct_reporting, contests };
  const json = new TextEncoder().encode(JSON.stringify(bundle));
  const cs = new CompressionStream("gzip"); const w = cs.writable.getWriter(); w.write(json); w.close();
  const gz = new Uint8Array(await new Response(cs.readable).arrayBuffer());
  let bin = ""; for (let i = 0; i < gz.length; i += 0x8000) bin += String.fromCharCode.apply(null, gz.subarray(i, i + 0x8000));
  return { ver, timestamp: bundle.timestamp, contests: contests.length, json_bytes: json.length, gz_bytes: gz.length, b64: btoa(bin) };
})();
