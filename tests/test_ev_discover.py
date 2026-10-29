"""discover_election_id: GA/ID publish their Nov 3 election object late; the orchestrator must only adopt an id when exactly one
non-recount election dated 2026-11-03 is listed. Offline: a fake session serves a jurisdiction payload shaped like the real
GA/ID responses (fields seen 2026-10-29: elections[] of {publicElectionId, name:[{languageId,text}], electionDate})."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import poll_enhanced_voting as pev  # noqa: E402


class _Resp:
    def __init__(self, obj, status=200):
        self.content = json.dumps(obj).encode()
        self.status_code = status


class _Session:
    def __init__(self, obj):
        self.obj, self.urls = obj, []

    def get(self, url, headers=None, timeout=None):
        self.urls.append(url)
        return _Resp(self.obj)


def _jur(*els):
    return {"id": "x", "name": [{"languageId": "en", "text": "Georgia"}],
            "elections": [{"publicElectionId": i, "name": [{"languageId": "en", "text": n}], "electionDate": d} for i, n, d in els]}


def test_pending_when_nov3_not_published():
    s = _Session(_jur(("08252026SpecialElectionRunoff", "August 25th, 2026 Special Election Runoff", "2026-08-25"),
                      ("GeneralPrimary51926", "May 19, 2026 - General Primary", "2026-05-19")))
    eid, cands = pev.discover_election_id("results.sos.ga.gov", "georgia", "2026-11-03", s, min_interval_s=0)
    assert eid is None and cands == []
    assert s.urls == ["https://results.sos.ga.gov/results/public/api/jurisdictions/georgia"]


def test_adopts_the_single_nov3_election():
    s = _Session(_jur(("2026NovGen", "November 3, 2026 - General Election", "2026-11-03"),
                      ("08252026SpecialElectionRunoff", "August 25th, 2026 Special Election Runoff", "2026-08-25")))
    eid, cands = pev.discover_election_id("results.sos.ga.gov", "georgia", "2026-11-03", s, min_interval_s=0)
    assert eid == "2026NovGen" and len(cands) == 1


def test_recount_entries_are_ignored_and_ambiguity_blocks():
    s = _Session(_jur(("2026NovGen", "November 3, 2026 - General Election", "2026-11-03"),
                      ("2026NovGenRecount", "RECOUNT - November 3, 2026", "2026-11-03")))
    eid, cands = pev.discover_election_id("results.sos.ga.gov", "georgia", "2026-11-03", s, min_interval_s=0)
    assert eid == "2026NovGen" and len(cands) == 2
    s2 = _Session(_jur(("A", "November 3, 2026 - General", "2026-11-03"), ("B", "November 3, 2026 - Special", "2026-11-03")))
    eid2, cands2 = pev.discover_election_id("results.voteidaho.gov", "id", "2026-11-03", s2, min_interval_s=0)
    assert eid2 is None and len(cands2) == 2  # two live candidates: a person decides, nothing is guessed


def test_every_active_source_has_an_implemented_poller():
    import json
    import poll_all
    srcs = json.load(open(os.path.join(os.path.dirname(HERE), "data", "sources.json")))["sources"]
    live = [s for s in srcs if s.get("active") and s.get("poller") not in (None, "none", "manual", "link_only")]
    missing = [(s["id"], s["poller"]) for s in live if s["poller"] not in poll_all.IMPLEMENTED]
    assert not missing, missing
