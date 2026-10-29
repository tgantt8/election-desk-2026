import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(ROOT, "tools", "hygiene_check.py")


def run(paths):
    return subprocess.run([sys.executable, CHECK, *paths], cwd=ROOT, capture_output=True, text=True)


def test_clean_file_passes(tmp_path):
    f = os.path.join(ROOT, "tests", "_tmp_clean.json")
    with open(f, "w") as fh:
        fh.write('{"contest": "Governor", "votes": 12, "source": "Macomb County Clerk"}')
    try:
        assert run([f]).returncode == 0
    finally:
        os.remove(f)


def test_token_fails():
    f = os.path.join(ROOT, "tests", "_tmp_token.py")
    with open(f, "w") as fh:
        fh.write('TOKEN = "ghp_' + "a" * 36 + '"\n')
    try:
        r = run([f])
        assert r.returncode == 1 and "GitHub personal access token" in r.stdout
    finally:
        os.remove(f)


def test_private_path_fails():
    d = os.path.join(ROOT, "tests", "_tmp_private")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "field_aggregates.json")
    with open(f, "w") as fh:
        fh.write("{}")
    try:
        r = run([f])
        assert r.returncode == 1 and "forbidden path" in r.stdout
    finally:
        os.remove(f)
        os.rmdir(d)


def test_phone_in_data_fails():
    f = os.path.join(ROOT, "tests", "_tmp_contact.csv")
    with open(f, "w") as fh:
        fh.write("zone,phone\nA,(586) 555-0100\n")
    try:
        r = run([f])
        assert r.returncode == 1 and "phone number" in r.stdout
    finally:
        os.remove(f)
