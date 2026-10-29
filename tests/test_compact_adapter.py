import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from macomb_compact_pdf import parse_compact_pdf_bytes  # noqa: E402
from macomb_parsers import parse_summary_pdf  # noqa: E402


def test_live_adapter_2024_hd58_matches_summary_report():
    raw = open(os.path.join(ROOT, "fixtures", "macomb_2024_general_official_summary.pdf"), "rb").read()
    out = parse_compact_pdf_bytes(raw)
    assert out["parse_status"] == "ok"
    hd = {r["candidate"]: r["votes"] for r in out["records"] if r["contest_id"] == "macomb-hd58" and not r["write_in"]}
    rep = parse_summary_pdf(os.path.join(ROOT, "fixtures", "macomb_2024_general_summary_elstats.pdf"))
    c = next(x for x in rep["contests"] if x["title"] == "Representative in State Legislature 58th District")
    for k in c["candidates"]:
        if not k["write_in"]:
            assert hd[k["name"]] == k["votes"]["TOTAL"]


def test_live_adapter_2026_template_yields_no_records():
    raw = open(os.path.join(ROOT, "fixtures", "macomb_2026_general_unofficial_summary_template.pdf"), "rb").read()
    out = parse_compact_pdf_bytes(raw)
    assert out["parse_status"] == "template_blank" and out["records"] == [] and out["contests"] > 100
