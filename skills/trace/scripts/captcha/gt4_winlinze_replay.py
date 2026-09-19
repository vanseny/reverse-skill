import argparse
import json
import random
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin

import requests


LOAD_URL = "https://gcaptcha4.geetest.com/load"
VERIFY_URL = "https://gcaptcha4.geetest.com/verify"
STATIC_BASE = "https://static.geetest.com/"
DEFAULT_CAPTCHA_ID = "54088bb07d2df3c46b79f80300b0abbe"


def callback():
    return f"geetest_{int(time.time() * 1000)}"


def parse_jsonp(text):
    match = re.fullmatch(r"\s*[^()]+\((.*)\)\s*;?\s*", text, re.S)
    if not match:
        raise ValueError(f"invalid JSONP: {text[:160]}")
    return json.loads(match.group(1))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_load_from_capture(path):
    snap = json.loads(Path(path).read_text(encoding="utf-8"))
    body = snap.get("responseBody", {}).get("text")
    if not body:
        raise ValueError("capture snapshot does not contain responseBody.text")
    parsed = parse_jsonp(body)
    return parsed, snap.get("query", {}).get("params", {}), snap.get("requestHeaders", {})


def winning_lines(size):
    for row in range(size):
        yield [(row, col) for col in range(size)]
    for col in range(size):
        yield [(row, col) for row in range(size)]
    yield [(index, index) for index in range(size)]
    yield [(index, size - 1 - index) for index in range(size)]


def line_winner(grid):
    for line in winning_lines(len(grid)):
        values = [grid[row][col] for row, col in line]
        if values[0] != 0 and all(value == values[0] for value in values):
            return {"value": values[0], "line": [list(item) for item in line]}
    return None


def solve_winlinze(ques):
    grid = [list(row) for row in ques]
    size = len(grid)
    if not grid or any(len(row) != size for row in grid):
        raise ValueError(f"winlinze expects a square board: {ques!r}")

    empties = [(row, col) for row in range(size) for col in range(size) if grid[row][col] == 0]
    pieces = [(row, col) for row in range(size) for col in range(size) if grid[row][col] != 0]
    for dst in empties:
        for src in pieces:
            candidate = [row[:] for row in grid]
            candidate[dst[0]][dst[1]] = candidate[src[0]][src[1]]
            candidate[src[0]][src[1]] = 0
            winner = line_winner(candidate)
            if winner:
                return {
                    "userresponse": [list(src), list(dst)],
                    "source": list(src),
                    "target": list(dst),
                    "piece": grid[src[0]][src[1]],
                    "winner": winner,
                    "board_after": candidate,
                }
    raise ValueError(f"no one-move win was found: {ques!r}")


def make_session(captcha_user=None, use_env_proxy=False):
    session = requests.Session()
    session.trust_env = use_env_proxy
    session.headers.update({
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://gt4.geetest.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    })
    if captcha_user:
        session.cookies.set("captcha_v4_user", captcha_user, domain=".geetest.com", path="/")
    return session


def request_load(session, captcha_id):
    params = {
        "callback": callback(),
        "captcha_id": captcha_id,
        "challenge": str(uuid.uuid4()),
        "client_type": "web",
        "risk_type": "winlinze",
        "lang": "zh",
    }
    response = session.get(LOAD_URL, params=params, timeout=30)
    response.raise_for_status()
    parsed = parse_jsonp(response.text)
    if parsed.get("status") != "success":
        raise RuntimeError(f"load failed: {parsed}")
    return parsed, response.text, params


def download_static(session, path):
    response = session.get(urljoin(STATIC_BASE, path), timeout=30)
    response.raise_for_status()
    return response.text


def build_w(args, data, userresponse, passtime, gct_file):
    helper_input = {
        "bundle": str(args.bundle.resolve()),
        "gctFile": str(gct_file.resolve()),
        "captchaId": args.captcha_id,
        "loadData": data,
        "userresponse": userresponse,
        "passtime": passtime,
    }
    proc = subprocess.run(
        ["node", str(args.helper.resolve())],
        input=json.dumps(helper_input, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"node helper failed:\n{proc.stderr}")
    return json.loads(proc.stdout)


def verify(session, captcha_id, data, w):
    params = {
        "callback": callback(),
        "captcha_id": captcha_id,
        "client_type": "web",
        "lot_number": data["lot_number"],
        "risk_type": data.get("captcha_type", "winlinze"),
        "payload": data["payload"],
        "process_token": data["process_token"],
        "payload_protocol": data["payload_protocol"],
        "pt": data["pt"],
        "w": w,
    }
    response = session.get(VERIFY_URL, params=params, timeout=30)
    response.raise_for_status()
    return parse_jsonp(response.text), response.text, params


def run_round(args, round_index):
    session = make_session(args.captcha_user, args.use_env_proxy)
    if args.from_capture:
        load_json, load_params, headers = extract_load_from_capture(args.from_capture)
        load_text = None
        if not args.captcha_user:
            cookie = headers.get("cookie") or headers.get("Cookie") or ""
            match = re.search(r"captcha_v4_user=([^;]+)", cookie)
            if match:
                session.cookies.set("captcha_v4_user", match.group(1), domain=".geetest.com", path="/")
        if not args.captcha_id and load_params.get("captcha_id"):
            args.captcha_id = load_params["captcha_id"]
    else:
        load_json, load_text, load_params = request_load(session, args.captcha_id)

    data = load_json["data"]
    cache = args.cache_root / data["lot_number"]
    cache.mkdir(parents=True, exist_ok=True)
    if load_text is not None:
        (cache / "load.jsonp").write_text(load_text, encoding="utf-8")
    save_json(cache / "load.json", load_json)
    save_json(cache / "load_params.json", load_params)
    save_json(cache / "cookies.json", requests.utils.dict_from_cookiejar(session.cookies))

    gct_file = args.gct
    if gct_file is None:
        gct_file = cache / "gct.raw.js"
        gct_file.write_text(download_static(session, data["gct_path"]), encoding="utf-8")

    solution = solve_winlinze(data["ques"])
    passtime = args.passtime if args.passtime is not None else random.randint(650, 1300)
    helper_output = build_w(args, data, solution["userresponse"], passtime, gct_file)
    save_json(cache / "solution.json", solution)
    save_json(cache / "helper_output.json", helper_output)

    summary = {
        "round": round_index,
        "lot_number": data["lot_number"],
        "captcha_type": data.get("captcha_type"),
        "ques": data["ques"],
        "userresponse": solution["userresponse"],
        "passtime": passtime,
        "fixed_fields": helper_output.get("fixedFields"),
        "lot_rules": helper_output.get("lotRules"),
        "lot_fields": helper_output.get("lotFields"),
        "w_length": len(helper_output["w"]),
        "cache": str(cache.resolve()),
    }
    if args.dry_run:
        summary["result"] = "dry-run"
        return summary

    time.sleep(passtime / 1000)
    verify_json, verify_text, verify_params = verify(session, args.captcha_id, data, helper_output["w"])
    (cache / "verify.jsonp").write_text(verify_text, encoding="utf-8")
    save_json(cache / "verify.json", verify_json)
    save_json(cache / "verify_params_meta.json", {k: (len(v) if k == "w" else v) for k, v in verify_params.items()})
    summary.update({
        "status": verify_json.get("status"),
        "result": verify_json.get("data", {}).get("result"),
        "fail_count": verify_json.get("data", {}).get("fail_count"),
    })
    return summary


def main():
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Geetest GT4 winlinze protocol replay")
    parser.add_argument("--captcha-id", default=DEFAULT_CAPTCHA_ID)
    parser.add_argument("--bundle", type=Path, default=base / "js_reverse_cache" / "gcaptcha4.raw.js")
    parser.add_argument("--helper", type=Path, default=base / "gt4_winlinze_helper.js")
    parser.add_argument("--gct", type=Path, help="optional local raw GCT file")
    parser.add_argument("--cache-root", type=Path, default=base / "js_reverse_cache" / "runs")
    parser.add_argument("--captcha-user", help="optional captcha_v4_user cookie value from browser")
    parser.add_argument("--from-capture", type=Path, help="browser network snapshot exported by js-reverse")
    parser.add_argument("--dry-run", action="store_true", help="build solution and w, but do not call /verify")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--passtime", type=int)
    parser.add_argument("--use-env-proxy", action="store_true")
    args = parser.parse_args()

    results = []
    for index in range(args.rounds):
        results.append(run_round(args, index + 1))
    print(json.dumps(results if args.rounds != 1 else results[0], ensure_ascii=False, indent=2))
    if any(item.get("result") not in ("success", "dry-run") for item in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
