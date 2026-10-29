/* Election Desk 2026 — static client. Reads ONLY the committed JSON under docs/data/.
   Layers never cross-write; the client only renders. */
(() => {
const DATA_FILES = ["meta","contests","ratings","polls","early_vote","results","calls","anomalies","baselines"];
const S = { data:{}, layer:"senate", colorby:"rating", tile:false, timer:null, lastFetch:null, geo:null };
const $ = (id) => document.getElementById(id);
const fmt = { n: (x) => x == null ? "—" : Number(x).toLocaleString("en-US"),
  pct: (x, d=1) => x == null ? "—" : (Number(x)).toFixed(d) + "%",
  m: (x) => x == null ? "—" : (x > 0 ? "D+" : x < 0 ? "R+" : "EVEN ") + Math.abs(x).toFixed(1),
  t: (iso) => iso ? new Date(iso).toLocaleString("en-US", { timeZone: "America/Detroit", month:"short", day:"numeric", hour:"numeric", minute:"2-digit" }) + " ET" : "—" };
const STATES = {AL:"Alabama",AK:"Alaska",AZ:"Arizona",AR:"Arkansas",CA:"California",CO:"Colorado",CT:"Connecticut",DE:"Delaware",FL:"Florida",GA:"Georgia",HI:"Hawaii",ID:"Idaho",IL:"Illinois",IN:"Indiana",IA:"Iowa",KS:"Kansas",KY:"Kentucky",LA:"Louisiana",ME:"Maine",MD:"Maryland",MA:"Massachusetts",MI:"Michigan",MN:"Minnesota",MS:"Mississippi",MO:"Missouri",MT:"Montana",NE:"Nebraska",NV:"Nevada",NH:"New Hampshire",NJ:"New Jersey",NM:"New Mexico",NY:"New York",NC:"North Carolina",ND:"North Dakota",OH:"Ohio",OK:"Oklahoma",OR:"Oregon",PA:"Pennsylvania",RI:"Rhode Island",SC:"South Carolina",SD:"South Dakota",TN:"Tennessee",TX:"Texas",UT:"Utah",VT:"Vermont",VA:"Virginia",WA:"Washington",WV:"West Virginia",WI:"Wisconsin",WY:"Wyoming",DC:"District of Columbia"};
const FIPS = {"01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE","11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA","20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN","28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA","54":"WV","55":"WI","56":"WY"};
// Tile map grid (row, col), 12 columns.
const TILE = {AK:[0,0],ME:[0,11],VT:[1,10],NH:[1,11],WA:[2,1],ID:[2,2],MT:[2,3],ND:[2,4],MN:[2,5],IL:[2,6],WI:[2,7],MI:[2,8],NY:[2,9],RI:[2,10],MA:[2,11],OR:[3,1],NV:[3,2],WY:[3,3],SD:[3,4],IA:[3,5],IN:[3,6],OH:[3,7],PA:[3,8],NJ:[3,9],CT:[3,10],CA:[4,1],UT:[4,2],CO:[4,3],NE:[4,4],MO:[4,5],KY:[4,6],WV:[4,7],VA:[4,8],MD:[4,9],DE:[4,10],AZ:[5,2],NM:[5,3],KS:[5,4],AR:[5,5],TN:[5,6],NC:[5,7],SC:[5,8],DC:[5,9],OK:[6,4],LA:[6,5],MS:[6,6],AL:[6,7],GA:[6,8],HI:[7,0],TX:[7,4],FL:[7,8]};

// ---------- fetch & refresh ----------
async function loadAll() {
  const bust = "?v=" + Date.now();
  const out = {};
  await Promise.all(DATA_FILES.map(async f => {
    try { const r = await fetch(`data/${f}.json${bust}`, { cache: "no-store" }); out[f] = r.ok ? await r.json() : null; }
    catch (e) { out[f] = null; }
  }));
  S.data = out; S.lastFetch = new Date();
  renderAll();
}
function setTimer() {
  if (S.timer) clearInterval(S.timer);
  const mins = Number($("interval").value);
  try { localStorage.setItem("desk.interval", String(mins)); } catch (e) {}
  if (mins > 0) S.timer = setInterval(loadAll, mins * 60000);
}
function staleCheck() {
  const meta = S.data.meta; const el = $("banner");
  if (!meta) { el.textContent = "No data yet — the poller has not published a snapshot."; el.classList.add("show"); return; }
  const last = meta.latest_snapshot_at ? new Date(meta.latest_snapshot_at) : null;
  const cadence = meta.expected_cadence_min || 60;
  const ageMin = last ? (Date.now() - last.getTime()) / 60000 : Infinity;
  if (!last) { el.textContent = "No snapshot published yet — the pollers have not run. Contest definitions and baselines are shown; live layers are empty."; el.classList.add("show"); }
  else if (ageMin > 2 * cadence) { el.textContent = `Stale data — last poll ${fmt.t(last.toISOString())} (${Math.round(ageMin)} min ago; expected every ${cadence} min). Check source health in Ops.`; el.classList.add("show"); }
  else el.classList.remove("show");
  $("lastpull").textContent = `Last poll ${last ? fmt.t(last.toISOString()) : "—"} · page refreshed ${fmt.t(S.lastFetch.toISOString())} · ${meta.built_at ? "data built " + fmt.t(meta.built_at) : ""}`;
}

// ---------- chambers ----------
function chamberBar(title, total, called, sim, marks, note) {
  const seg = (n, cls) => n > 0 ? `<div class="seg ${cls}" style="width:${(100*n/total).toFixed(2)}%"></div>` : "";
  const d = called.d||0, r = called.r||0, i = called.i||0, sd = sim?.d||0, sr = sim?.r||0;
  const unc = Math.max(0, total - d - r - i - sd - sr);
  return `<div class="chamber"><div class="label"><span><strong>${title}</strong> <span class="muted small">${note||""}</span></span>
    <span class="mono">D ${d}${i?` (+${i} I)`:""} · R ${r} · uncalled ${unc}${sd+sr?` · sim D ${sd} / R ${sr}`:""}</span></div>
    <div class="bar">${seg(d,"d")}${seg(i,"i")}${seg(sd,"dsim")}<div class="seg" style="flex:1"></div>${seg(sr,"rsim")}${seg(r,"r")}
    ${marks.map(m=>`<div class="mark" style="left:${(100*m.at/total).toFixed(2)}%"></div>`).join("")}</div>
    <div class="marks">${marks.map((m,i)=>`<span style="left:${(100*m.at/total).toFixed(2)}%;top:${i%2?12:0}px">${m.label}</span>`).join("")}</div></div>`;
}
function renderChambers() {
  const c = S.data.contests?.chambers; const el = $("chambers");
  if (!c) { el.innerHTML = '<p class="muted">No chamber data.</p>'; return; }
  const res = S.data.results?.chamber_calls || { senate:{d:0,r:0,i:0}, house:{d:0,r:0,i:0} };
  const sim = S.data.contests?.sim_chambers || null;
  // Seats not up in 2026 carry over: show them as "called" for the party holding them (holdovers), labeled.
  const hold = c.senate.holdovers || {d:0,r:0,i:0};
  const sen = { d: hold.d + (res.senate?.d||0), r: hold.r + (res.senate?.r||0), i: hold.i + (res.senate?.i||0) };
  el.innerHTML = chamberBar("Senate", 100, sen, sim?.senate, [{at:50,label:"50 · VP tiebreak "+c.senate.vp_tiebreak_party},{at:51,label:"51 = majority"}],
      `holdovers ${hold.d}D/${hold.r}R/${hold.i}I + 2026 calls; independents shown with caucus`)
    + chamberBar("House", 435, { d: res.house?.d||0, r: res.house?.r||0, i: res.house?.i||0 }, sim?.house, [{at:218,label:"218"}], "all 435 seats up");
  $("chambers-src").innerHTML = `Starting balance (pre-election): Senate ${c.senate.republican}R / ${c.senate.democrat}D / ${c.senate.independent}I (caucus D), ${c.senate.vacancies} vacant — ${c.senate.source.name}, retrieved ${fmt.t(c.senate.source.retrieved_at)}. House ${c.house.republican}R / ${c.house.democrat}D / ${c.house.independent}I, ${c.house.vacancies} vacant (${c.house.vacant_seats.map(v=>v.district).join(", ")}) — ${c.house.source.name}, retrieved ${fmt.t(c.house.source.retrieved_at)}. Calls: ${S.data.calls?.records?.length||0} recorded, each attributed to its outlet and time. UNOFFICIAL.`;
}

// ---------- map ----------
function lerp(x) { const a=[239,68,68], b=[59,130,246]; return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*x)).join(",")})`; }
const RATING_COLOR = { "-3":"#1d4ed8","-2":"#3b82f6","-1":"#93c5fd","0":"#d6b400","1":"#fca5a5","2":"#ef4444","3":"#b91c1c" };
function stateInfo(abbr) {
  const con = S.data.contests || {};
  const races = S.layer === "senate" ? (con.senate_2026||[]).filter(r=>r.state===abbr)
             : S.layer === "gov" ? (con.governors_2026||[]).filter(r=>r.state===abbr)
             : (con.house_delegations||[]).filter(r=>r.state===abbr);
  return races;
}
function stateColor(abbr) {
  const races = stateInfo(abbr);
  if (!races.length) return null; // no race → hatch
  const r = races[0];
  if (S.layer === "house") {
    const d = r.current?.d ?? 0, rr = r.current?.r ?? 0; const tot = d + rr || 1;
    return lerp(d / tot);
  }
  if (S.colorby === "rating") { const sc = r.rating_scale; return sc == null ? "#4b5563" : RATING_COLOR[String(sc)]; }
  if (S.colorby === "poll") { const m = r.poll_margin; return m == null ? "#4b5563" : lerp(Math.max(0, Math.min(1, (m + 15) / 30))); }
  if (S.colorby === "result") { const m = r.result_margin; return m == null ? "#4b5563" : (m > 0 ? "#3b82f6" : m < 0 ? "#ef4444" : "#d6b400"); }
  if (S.colorby === "sim") { const p = r.sim_p_dem; return p == null ? "#4b5563" : lerp(p); }
  return "#4b5563";
}
async function ensureGeo() {
  if (S.geo) return S.geo;
  const url = "vendor/us-atlas-3.0.1-states-10m.json"; // us-atlas 3.0.1 (vendored; no CDN dependency on election night)
  const topo = await (await fetch(url)).json();
  S.geo = topojson.feature(topo, topo.objects.states);
  return S.geo;
}
async function renderMap() {
  if (typeof d3 === "undefined" || typeof topojson === "undefined") { // CDN unreachable: fall back to the tile map
    if (!S.tile) { S.tile = true; $("map-geo").style.display = "none"; $("map-tile").style.display = "grid"; $("maptoggle").textContent = "Geo map"; $("maptoggle").disabled = true; }
    renderTile(); return;
  }
  const svg = d3.select("#map"); svg.selectAll("*").remove();
  svg.append("defs").html('<pattern id="hatch" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)"><rect width="6" height="6" fill="#2a3346"/><line x1="0" y1="0" x2="0" y2="6" stroke="#3b4660" stroke-width="2"/></pattern>');
  let geo; try { geo = await ensureGeo(); } catch (e) { svg.append("text").attr("x",20).attr("y",40).attr("fill","#9aa4b2").text("Map tiles unavailable (offline) — use Tile map."); return; }
  const path = d3.geoPath(d3.geoAlbersUsa().scale(1300).translate([487.5, 305]));
  svg.append("g").selectAll("path").data(geo.features).join("path")
    .attr("class", d => "state" + (stateColor(FIPS[d.id]) ? "" : " norace"))
    .attr("d", path).attr("fill", d => stateColor(FIPS[d.id]) || undefined)
    .on("click", (e, d) => openState(FIPS[d.id]))
    .append("title").text(d => STATES[FIPS[d.id]] || d.id);
  renderTile();
}
function renderTile() {
  const tile = $("map-tile"); tile.innerHTML = "";
  for (let r = 0; r < 8; r++) for (let c = 0; c < 12; c++) {
    const ab = Object.keys(TILE).find(k => TILE[k][0] === r && TILE[k][1] === c);
    const div = document.createElement("div");
    if (!ab) div.className = "empty"; else { div.textContent = ab; const col = stateColor(ab); div.style.background = col || "repeating-linear-gradient(45deg,#2a3346 0 3px,#3b4660 3px 6px)"; div.onclick = () => openState(ab); }
    tile.appendChild(div);
  }
  $("map-legend").innerHTML = S.layer === "house"
    ? '<span><i class="sw" style="background:#3b82f6"></i>D delegation</span><span><i class="sw" style="background:#ef4444"></i>R delegation</span><span><i class="sw" style="background:repeating-linear-gradient(45deg,#2a3346 0 3px,#3b4660 3px 6px)"></i>no data</span>'
    : Object.entries({"Solid D":"-3","Likely D":"-2","Lean D":"-1","Toss-up":"0","Lean R":"1","Likely R":"2","Solid R":"3"}).map(([k,v])=>`<span><i class="sw" style="background:${RATING_COLOR[v]}"></i>${k}</span>`).join("") + '<span><i class="sw" style="background:repeating-linear-gradient(45deg,#2a3346 0 3px,#3b4660 3px 6px)"></i>no race</span>';
  const r = S.data.ratings; $("map-src").textContent = S.colorby === "rating" ? `Rating: ${r?.primary_rater || "Cook Political Report"}, ${r?.as_of ? fmt.t(r.as_of) : "date on each race"}. Labels and dates only, linked to the publisher. UNOFFICIAL.` : S.colorby === "result" ? "Live result margins from official state election offices. UNOFFICIAL until certified." : S.colorby === "poll" ? "Desk polling average (weights shown on Polls tab) next to published averages." : "Simulator: Internal estimate — not a call — do not share.";
}
function openState(ab) {
  const races = stateInfo(ab); const body = $("drawer-body");
  const con = S.data.contests || {}; const nl = (con.new_lines?.in_effect_2026 || []).find(x => x.state === ab);
  let h = `<h2>${STATES[ab] || ab} ${nl ? '<span class="pill">new lines 2026</span>' : ''}</h2>`;
  if (!races.length) h += '<p class="muted">No race in this layer for 2026.</p>';
  for (const r of races) {
    h += `<div class="card"><h3>${r.office || r.title || ""}${r.special ? " (special)" : ""}</h3>`;
    if (r.candidates) h += `<p>${r.candidates.map(c=>`<span class="pill ${(c.party||"").toLowerCase().startsWith("d")?"d":(c.party||"").toLowerCase().startsWith("r")?"r":""}">${c.name} (${c.party||"?"})${c.incumbent?" · inc.":""}</span>`).join(" ")}</p>`;
    if (r.ratings) h += `<dl class="kv">${r.ratings.map(x=>`<dt>${x.rater}</dt><dd>${x.label} <span class="muted small">${x.date||""}</span> ${x.url?`<a href="${x.url}" target="_blank" rel="noopener">link</a>`:""}</dd>`).join("")}</dl>`;
    if (r.current) h += `<p>Current delegation D ${r.current.d} – R ${r.current.r}${r.current.i?` – I ${r.current.i}`:""}${r.current.vacant?` (${r.current.vacant} vacant)`:""}</p>`;
    if (r.districts) h += `<div class="tablewrap"><table><tr><th>District</th><th>Incumbent</th><th>Rating</th><th class="num">2024 pres. margin</th><th>Lines</th></tr>${r.districts.map(d=>`<tr><td>${d.id}</td><td>${d.incumbent||"open"}</td><td>${d.rating||"—"}</td><td class="num">${d.pres_2024_margin==null?'<span class="muted">no baseline</span>':fmt.m(d.pres_2024_margin)}</td><td>${d.new_lines?"new":""}</td></tr>`).join("")}</table></div>`;
    if (r.status) h += `<p><span class="status">${r.status}</span></p>`;
    if (r.result) h += `<p class="mono">${r.result.summary||""}</p><div class="src">${r.result.source||""} · ${fmt.t(r.result.as_of)} · UNOFFICIAL</div>`;
    h += `<div class="row" style="margin-top:6px"><button class="btn" onclick="window.deskCopy(${JSON.stringify(ab)},${JSON.stringify(r.id||"")})">Copy for Slack</button></div></div>`;
  }
  body.innerHTML = h; $("drawer").classList.add("open");
}
window.deskCopy = (ab, id) => {
  const races = stateInfo(ab); const r = races.find(x => x.id === id) || races[0]; if (!r) return;
  const lines = [`${STATES[ab]} — ${r.office || ""}${r.special?" (special)":""}`];
  if (r.ratings) for (const x of r.ratings) lines.push(`Rating: ${x.rater}, ${x.date||""}: ${x.label} ${x.url||""}`);
  if (r.result) lines.push(`${r.result.summary} — ${r.result.source} as of ${fmt.t(r.result.as_of)}`);
  if (r.status) lines.push(`Status: ${r.status}`);
  lines.push(`UNOFFICIAL until certified. Desk pulled ${fmt.t(S.data.meta?.latest_snapshot_at)}.`);
  navigator.clipboard?.writeText(lines.join("\n"));
};

// ---------- other views (data-driven; populated as layers land) ----------
function table(el, cols, rows, empty) {
  if (!rows || !rows.length) { el.innerHTML = `<tr><td class="muted">${empty||"No records yet."}</td></tr>`; return; }
  el.innerHTML = `<tr>${cols.map(c=>`<th class="${c.num?"num":""}">${c.h}</th>`).join("")}</tr>` + rows.map(r=>`<tr>${cols.map(c=>`<td class="${c.num?"num":""}">${c.f(r)}</td>`).join("")}</tr>`).join("");
}
function renderPolls() {
  const p = S.data.polls; const avg = $("polls-avg");
  if (!p) { avg.innerHTML = '<p class="muted">Polls layer not published yet (P2).</p>'; table($("polls-table"),[],[]); return; }
  const sel = $("polls-race"); const races = Object.keys(p.averages||{});
  if (sel.options.length !== races.length) sel.innerHTML = races.map(r=>`<option>${r}</option>`).join("");
  const race = sel.value || races[0]; const a = p.averages?.[race];
  avg.innerHTML = a ? `<div class="kv"><dt>Desk average</dt><dd><strong>${fmt.m(a.margin)}</strong> <span class="small muted">n=${a.n_polls}, weights: half-life ${a.weights.half_life_days}d · √n · LV×${a.weights.lv_pref} · grade×${a.weights.grade_mult} · house effects ${a.weights.house_effects?"on":"off"}</span></dd>
    ${(a.published||[]).map(x=>`<dt>${x.name}</dt><dd>${x.value!=null?fmt.m(x.value):"—"} <a href="${x.url}" target="_blank" rel="noopener">link</a> <span class="small muted">${x.as_of||""}</span></dd>`).join("")}</div>` : "";
  const days = Number($("polls-days").value), pop = $("polls-pop").value;
  const cutoff = Date.now() - days*86400000;
  const rows = (p.records||[]).filter(r => r.race===race && (!pop || r.population===pop) && new Date(r.field_end).getTime() >= cutoff);
  table($("polls-table"), [{h:"Pollster",f:r=>`<a href="${r.url}" target="_blank" rel="noopener">${r.pollster}</a>${r.sponsor?`<div class="small muted">${r.sponsor}</div>`:""}`},{h:"Field",f:r=>`${r.field_start}–${r.field_end}`},{h:"Pop",f:r=>`${r.population}${r.n?` n=${r.n}`:""}`},{h:"Margin",num:true,f:r=>fmt.m(r.margin)},{h:"Grade",f:r=>r.grade?`${r.grade} <span class="small muted">(${r.grade_source})</span>`:'<span class="muted">ungraded</span>'}], rows, "No polls match.");
  $("polls-dedupe").innerHTML = (p.dedupe_log||[]).slice(-20).map(x=>`${x.at}: ${x.note}`).join("<br>") || "No duplicates seen.";
}
function renderRatings() {
  const r = S.data.ratings;
  table($("ratings-table"), [{h:"Race",f:x=>x.race},{h:"Rater",f:x=>x.rater},{h:"Label",f:x=>x.label},{h:"Date",f:x=>x.date||""},{h:"",f:x=>x.url?`<a href="${x.url}" target="_blank" rel="noopener">link</a>`:""}], r?.latest||[], "Ratings layer not published yet.");
  $("ratings-changes").innerHTML = (r?.changes||[]).slice(-30).reverse().map(c=>`${c.date}: ${c.race} — ${c.rater}: ${c.from||"—"} → ${c.to}`).join("<br>") || '<span class="muted">No changes logged.</span>';
  const ev = S.data.early_vote;
  table($("ev-table"), [{h:"Geography",f:x=>x.geography},{h:"Metric",f:x=>x.metric},{h:"Value",num:true,f:x=>fmt.n(x.value)},{h:"vs 2022",num:true,f:x=>x.vs_2022==null?'<span class="muted">no baseline</span>':fmt.n(x.vs_2022)},{h:"vs 2024",num:true,f:x=>x.vs_2024==null?'<span class="muted">no baseline</span>':fmt.n(x.vs_2024)},{h:"As of",f:x=>`${x.as_of||""}<div class="small muted">${x.source||""}</div>`}], ev?.records||[], "Early-vote layer not published yet.");
}
function raceCard(r) {
  const tot = (r.candidates||[]).reduce((s,c)=>s+(c.votes||0),0) || 1;
  const modes = r.modes ? `<div class="modebar">${Object.entries(r.modes).map(([k,v])=>`<span title="${k}: ${fmt.n(v)}" style="width:${(100*v/Math.max(1,Object.values(r.modes).reduce((a,b)=>a+b,0))).toFixed(1)}%;background:${{AVCB:"#60a5fa",ED:"#f59e0b",EV:"#a78bfa",Total:"#4b5563"}[k]||"#4b5563"}"></span>`).join("")}</div><div class="small muted">${Object.keys(r.modes).join(" · ")}</div>` : "";
  return `<div class="card"><div class="row" style="justify-content:space-between"><strong>${r.title}</strong><span class="status">${r.status||"Too early"}</span></div>
    ${(r.candidates||[]).map(c=>`<div class="row" style="justify-content:space-between"><span class="pill ${(c.party||"").startsWith("D")?"d":(c.party||"").startsWith("R")?"r":""}">${c.name} (${c.party})</span><span class="mono">${fmt.n(c.votes)} · ${fmt.pct(100*(c.votes||0)/tot)}</span></div>`).join("")}
    <div class="row small muted" style="justify-content:space-between"><span>margin ${r.margin!=null?fmt.m(r.margin):"—"}</span><span>${r.reporting_pct!=null?fmt.pct(r.reporting_pct,0)+" reporting":""}${r.precincts?` · ${r.precincts}`:""}</span><span>${r.delta!=null?`Δ ${r.delta>0?"+":""}${r.delta.toFixed(1)} since last pull`:""}</span></div>
    ${modes}<div class="src">${r.source||""} · ${fmt.t(r.as_of)} · UNOFFICIAL${r.county_scope==="macomb_portion"?" · Macomb portion only":""}</div></div>`;
}
function renderResults() {
  const res = S.data.results;
  $("results-national").innerHTML = (res?.national||[]).map(raceCard).join("") || '<p class="muted">No national results yet. Polls close from 7 PM ET Nov 3.</p>';
  $("results-macomb").innerHTML = (res?.macomb_tier1||[]).map(raceCard).join("") || '<p class="muted">No Macomb results yet. Michigan polls close 8 PM ET Nov 3.</p>';
}
function renderMacomb() {
  const res = S.data.results; const sel = $("macomb-contest");
  const contests = res?.macomb_detail ? Object.keys(res.macomb_detail) : [];
  if (sel.options.length !== contests.length) sel.innerHTML = contests.map(c=>`<option>${c}</option>`).join("");
  const c = res?.macomb_detail?.[sel.value || contests[0]];
  table($("macomb-table"), [{h:"Precinct",f:x=>x.unit},{h:"Mode",f:x=>x.mode},{h:"Candidate",f:x=>x.candidate},{h:"Votes",num:true,f:x=>fmt.n(x.votes)},{h:"Complete",f:x=>x.complete?"✓":""}], c?.rows||[], "No precinct rows yet.");
  $("macomb-timeline").innerHTML = (res?.macomb_snapshots||[]).slice(-30).reverse().map(s=>`${fmt.t(s.fetched_at)} · ${s.parse_status} · <span class="mono">${(s.raw_hash||"").slice(0,10)}</span>`).join("<br>") || '<span class="muted">No snapshots.</span>';
  const an = S.data.anomalies?.records || [];
  $("anomalies").innerHTML = an.length ? an.map(a=>`<div class="flag"><strong>${a.type}</strong> — ${a.unit} <span class="status">${a.status}</span><div class="small">${a.detail} Data changed — confirm with the Clerk.</div><div class="small muted">${fmt.t(a.at)}</div></div>`).join("") : '<p class="muted">No open flags.</p>';
}
function renderOps() {
  const m = S.data.meta;
  $("ops-health").innerHTML = m?.sources?.length ? `<div class="tablewrap"><table><tr><th></th><th>Source</th><th>Layer</th><th>Status</th><th>Last success</th><th>Error</th></tr>${m.sources.map(s=>`<tr><td><i class="health ${s.health}"></i></td><td><a href="${s.url}" target="_blank" rel="noopener">${s.name}</a><div class="small muted">${s.terms_note||""}</div></td><td>${s.layer}</td><td class="small">${s.status||""}<div class="muted">${s.poller||""}</div></td><td class="small">${fmt.t(s.last_success_at)}</td><td class="small muted">${s.last_error||""}</td></tr>`).join("")}</table></div>` : '<p class="muted">Source registry not published yet.</p>';
  $("exports").innerHTML = DATA_FILES.map(f=>`<a class="btn" href="data/${f}.json" download>${f}.json</a>`).join("");
}
function renderAll() { staleCheck(); renderChambers(); renderMap(); renderPolls(); renderRatings(); renderResults(); renderMacomb(); renderOps(); }

// ---------- manual panels ----------
function parsePaste() {
  const txt = $("paste").value; const rows = [];
  for (const line of txt.split(/\r?\n/)) {
    const cells = line.includes(",") ? line.split(",") : line.trim().split(/\s{2,}|\t/);
    const nums = cells.map(c=>c.trim().replace(/,/g,"")).filter(c=>/^\d+$/.test(c));
    if (cells.length >= 2 && nums.length) rows.push({ label: cells[0].trim(), numbers: nums.map(Number) });
  }
  const out = { layer: "results", entered_by: "manual-paste", entered_at: new Date().toISOString(), note: "Manual entry — verify against the source before use. UNOFFICIAL.", rows };
  $("paste-out").textContent = JSON.stringify(out, null, 1); return out;
}
function callJson() {
  const out = { layer:"calls", contest: $("call-contest").value, outlet: $("call-outlet").value, called_for: $("call-for").value, called_at: $("call-time").value ? new Date($("call-time").value).toISOString() : null, url: $("call-url").value, entered_by: "call-entry-form", entered_at: new Date().toISOString(), status: "Projected" };
  $("call-out").textContent = JSON.stringify(out, null, 1); return out;
}

// ---------- wiring ----------
document.querySelectorAll("nav.bottom button").forEach(b => b.onclick = () => { document.querySelectorAll("nav.bottom button").forEach(x=>x.classList.toggle("active", x===b)); document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active", v.id==="view-"+b.dataset.view)); try{localStorage.setItem("desk.view",b.dataset.view)}catch(e){} });
document.querySelectorAll("#layer-tabs button").forEach(b => b.onclick = () => { document.querySelectorAll("#layer-tabs button").forEach(x=>x.classList.toggle("active",x===b)); S.layer = b.dataset.layer; renderMap(); });
$("colorby").onchange = e => { S.colorby = e.target.value; renderMap(); };
$("maptoggle").onclick = () => { S.tile = !S.tile; $("map-geo").style.display = S.tile ? "none" : ""; $("map-tile").style.display = S.tile ? "grid" : "none"; $("maptoggle").textContent = S.tile ? "Geo map" : "Tile map"; };
$("refresh").onclick = loadAll; $("interval").onchange = setTimer;
$("theme").onclick = () => { const h = document.documentElement; const next = h.dataset.theme === "dark" ? "light" : "dark"; h.dataset.theme = next; try{localStorage.setItem("desk.theme",next)}catch(e){} };
["polls-race","polls-pop","polls-days"].forEach(id => $(id).onchange = renderPolls); $("macomb-contest").onchange = renderMacomb;
$("paste-parse").onclick = parsePaste; $("paste-copy").onclick = () => navigator.clipboard?.writeText(JSON.stringify(parsePaste()));
$("call-copy").onclick = () => navigator.clipboard?.writeText(JSON.stringify(callJson()));
try { const iv = localStorage.getItem("desk.interval"); if (iv !== null) $("interval").value = iv; const th = localStorage.getItem("desk.theme"); if (th) document.documentElement.dataset.theme = th; const v = localStorage.getItem("desk.view"); if (v) document.querySelector(`nav.bottom button[data-view="${v}"]`)?.click(); } catch (e) {}
if (window.matchMedia && window.matchMedia("(max-width: 520px)").matches && !S.geo) { /* mobile default: tile map after first render */ }
setTimer(); loadAll();
})();
