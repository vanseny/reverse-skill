import argparse
import hashlib
import json
import re
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urljoin

import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad


LOAD_URL = "https://gcaptcha4.geetest.com/load"
VERIFY_URL = "https://gcaptcha4.geetest.com/verify"
DEMO_LOGIN_URL = "https://gt4.geetest.com/demo/login"
STATIC_BASE = "https://static.geetest.com/"
DEFAULT_CAPTCHA_ID = "54088bb07d2df3c46b79f80300b0abbe"

RSA_N_HEX = (
    "c1e3934d1614465b33053e7f48ee4ec87b14b95ef88947713d25eecbff7e74c"
    "7977d02dc1d9451f79dd5d1c10c29acb6a9b4d6fb7d0a0279b6719e1772565f"
    "09af627715919221aef91899cae08c0d686d748b20a3603be2318ca6bc2b597"
    "06592a9219d0bf05c9f65023a21d2330807252ae0066d59ceefa5f2748ea80bab81"
)
RSA_E = 65537

GEE_GUARD = {
    "roe": {
        "aup": "3",
        "sep": "3",
        "egp": "3",
        "auh": "3",
        "rew": "3",
        "snh": "3",
        "res": "3",
        "cdc": "3",
    }
}
EM = {"ph": 0, "cp": 0, "ek": "11", "wd": 1, "nt": 0, "si": 0, "sc": 0}


def callback() -> str:
    return f"geetest_{int(time.time() * 1000)}"


def parse_jsonp(text: str) -> dict:
    match = re.fullmatch(r"\s*[^(]+\((.*)\)\s*;?\s*", text, re.S)
    if not match:
        raise ValueError(f"Invalid JSONP: {text[:160]}")
    return json.loads(match.group(1))


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def decode_uri_bytes(value: str) -> bytes:
    reserved = b";/?:@&=+$,#"
    result = bytearray()
    index = 0
    while index < len(value):
        if value[index] == "%" and index + 2 < len(value):
            decoded = int(value[index + 1:index + 3], 16)
            if decoded in reserved:
                result.extend(value[index:index + 3].encode("ascii"))
            else:
                result.append(decoded)
            index += 3
        else:
            result.extend(value[index].encode("utf-8"))
            index += 1
    return bytes(result)


def decode_string_table(source: str) -> list[str]:
    encoded_match = re.search(r"decodeURI\((['\"])(.*?)\1\)", source)
    if not encoded_match:
        raise ValueError("String table was not found")
    tail = source[encoded_match.end():encoded_match.end() + 3000]
    key_match = re.search(r"\}\((['\"])(.*?)\1\)\s*\n?\s*\}", tail)
    if not key_match:
        raise ValueError("String-table XOR key was not found")
    encoded = decode_uri_bytes(encoded_match.group(2))
    key = key_match.group(2).encode("latin1")
    decoded = bytes(value ^ key[index % len(key)] for index, value in enumerate(encoded))
    return decoded.decode("latin1").split("^")


def extract_bundle_metadata(bundle_path: Path) -> tuple[dict, dict]:
    source = bundle_path.read_text(encoding="utf-8")
    strings = decode_string_table(source)
    lot_match = re.search(
        r"['\"](n\[[^'\"]+)['\"]\s*:\s*[^\n]*?\((\d+)\)",
        source,
    )
    region_start = max(0, lot_match.start() - 3000) if lot_match else 0
    metadata_region = source[region_start:lot_match.end() + 500] if lot_match else ""
    fixed_match = re.search(
        r"\]\s*=\s*\{\s*([A-Za-z_$][A-Za-z0-9_$]*):\s*[^\n]*?\((\d+)\)\s*\}",
        metadata_region,
    )
    if not fixed_match or not lot_match:
        raise ValueError("Current bundle metadata initialization was not recognized")
    fixed_fields = {fixed_match.group(1): strings[int(fixed_match.group(2))]}
    lot_rules = {lot_match.group(1): strings[int(lot_match.group(2))]}
    return fixed_fields, lot_rules


def resolve_lot_expression(expression: str, lot_number: str) -> str:
    def replace(match: re.Match) -> str:
        start, end = map(int, match.groups())
        return lot_number[start:end + 1]

    return re.sub(r"n\[(\d+):(\d+)\]", replace, expression).replace("+", "")


def resolve_lot_fields(lot_number: str, rules: dict) -> dict:
    result = {}
    for key_expression, value_expression in rules.items():
        path = resolve_lot_expression(key_expression, lot_number).split(".")
        value = resolve_lot_expression(value_expression, lot_number)
        target = result
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = value
    return result


def extract_function(source: str, start: int) -> str:
    brace = source.find("{", start)
    if brace < 0:
        raise ValueError("Function opening brace was not found")
    depth = 0
    quote = None
    escaped = False
    for index in range(brace, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise ValueError("Function closing brace was not found")


def int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value if value < 0x80000000 else value - 0x100000000


def js_5381_hash(value: str) -> int:
    state = 5381
    utf16 = value.encode("utf-16-le", "surrogatepass")
    for index in range(0, len(utf16), 2):
        code_unit = int.from_bytes(utf16[index:index + 2], "little")
        state = int32(state) * 33 + code_unit
    return int32(state) & 0x7FFFFFFF


def calculate_biht(gct_source: str) -> str:
    marker = gct_source.find("=5381;")
    if marker < 0:
        raise ValueError("GCT 5381 hash function was not found")
    hash_start = gct_source.rfind("function ", 0, marker)
    if hash_start < 0:
        raise ValueError("GCT hash function start was not found")
    hash_source = extract_function(gct_source, hash_start)
    hash_end = hash_start + len(hash_source)
    guard_match = re.search(r"function\s+\w+\(\w+\)\{", gct_source[hash_end:])
    if not guard_match:
        raise ValueError("GCT guard function was not found")
    guard_source = extract_function(gct_source, hash_end + guard_match.start())
    suffix = decode_string_table(gct_source)[78]
    return str(js_5381_hash(guard_source + str(js_5381_hash(hash_source)))) + suffix


def solve_pow(captcha_id: str, lot_number: str, detail: dict) -> dict:
    hashfunc = detail["hashfunc"].lower()
    if hashfunc != "sha256":
        raise ValueError(f"Unsupported PoW hash: {hashfunc}")
    prefix = "|".join([
        str(detail["version"]),
        str(detail["bits"]),
        hashfunc,
        detail["datetime"],
        captcha_id,
        lot_number,
        "",
    ]) + "|"
    target = 1 << (256 - int(detail["bits"]))
    while True:
        message = prefix + secrets.token_hex(8)
        digest = hashlib.sha256(message.encode()).hexdigest()
        if int(digest, 16) < target:
            return {"pow_msg": message, "pow_sign": digest}


def encrypt_w(payload: dict, pt: str) -> tuple[str, str]:
    if str(pt) != "1":
        raise ValueError(f"This replay supports pt=1, got {pt}")
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    aes_key = secrets.token_hex(8).encode()
    aes_hex = AES.new(aes_key, AES.MODE_CBC, b"0000000000000000").encrypt(
        pad(compact.encode(), AES.block_size)
    ).hex()
    public_key = RSA.construct((int(RSA_N_HEX, 16), RSA_E))
    rsa_hex = PKCS1_v1_5.new(public_key).encrypt(aes_key).hex()
    return aes_hex + rsa_hex, compact


def download_static(session: requests.Session, path_or_url: str) -> requests.Response:
    response = session.get(urljoin(STATIC_BASE, path_or_url), timeout=30)
    response.raise_for_status()
    return response


def prepare_session(args: argparse.Namespace) -> requests.Session:
    session = requests.Session()
    session.trust_env = args.use_env_proxy
    session.headers.update({
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://gt4.geetest.com/",
        "User-Agent": args.user_agent,
        "sec-ch-ua": args.sec_ch_ua,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    })
    captcha_user = args.captcha_user or secrets.token_hex(16)
    session.cookies.set("captcha_v4_user", captcha_user, domain=".geetest.com", path="/")
    return session


def build_w_payload(captcha_id: str, data: dict, fixed_fields: dict, lot_rules: dict, biht: str) -> dict:
    pow_data = solve_pow(captcha_id, data["lot_number"], data["pow_detail"])
    return {
        "device_id": "",
        "lot_number": data["lot_number"],
        **pow_data,
        "geetest": "captcha",
        "lang": "zh",
        "ep": "123",
        "biht": biht,
        "gee_guard": GEE_GUARD,
        **fixed_fields,
        **resolve_lot_fields(data["lot_number"], lot_rules),
        "em": EM,
    }


def replay_once(args: argparse.Namespace) -> tuple[dict, Path]:
    fixed_fields, lot_rules = extract_bundle_metadata(args.bundle)
    session = prepare_session(args)
    load_params = {
        "callback": callback(),
        "captcha_id": args.captcha_id,
        "challenge": args.challenge or str(uuid.uuid4()),
        "client_type": "web",
        "risk_type": "ai",
        "lang": "zh",
    }
    load_response = session.get(LOAD_URL, params=load_params, timeout=30)
    load_response.raise_for_status()
    load_json = parse_jsonp(load_response.text)
    if load_json.get("status") != "success":
        raise RuntimeError(f"Load failed: {load_json}")
    data = load_json["data"]
    if data.get("captcha_type") != "ai":
        raise RuntimeError(f"Expected captcha_type=ai, got {data.get('captcha_type')!r}")

    cache = args.cache_root / data["lot_number"]
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "load.jsonp").write_text(load_response.text, encoding="utf-8")
    save_json(cache / "load.json", load_json)
    save_json(cache / "load_request.json", {"url": load_response.url, "params": load_params})
    save_json(cache / "cookies.json", requests.utils.dict_from_cookiejar(session.cookies))

    gct_response = download_static(session, data["gct_path"])
    gct_source = gct_response.text
    (cache / "gct.raw.js").write_text(gct_source, encoding="utf-8")
    biht = calculate_biht(gct_source)
    w_payload = build_w_payload(args.captcha_id, data, fixed_fields, lot_rules, biht)
    w, compact = encrypt_w(w_payload, str(data["pt"]))
    save_json(cache / "w_payload.json", w_payload)
    save_json(cache / "replay_meta.json", {
        "compact": compact,
        "w": w,
        "w_length": len(w),
        "biht": biht,
        "fixed_fields": fixed_fields,
        "lot_rules": lot_rules,
        "lot_fields": resolve_lot_fields(data["lot_number"], lot_rules),
    })

    verify_params = {
        "callback": callback(),
        "captcha_id": args.captcha_id,
        "client_type": "web",
        "lot_number": data["lot_number"],
        "risk_type": data["captcha_type"],
        "payload": data["payload"],
        "process_token": data["process_token"],
        "payload_protocol": data["payload_protocol"],
        "pt": data["pt"],
        "w": w,
    }
    verify_response = session.get(VERIFY_URL, params=verify_params, timeout=30)
    verify_response.raise_for_status()
    verify_json = parse_jsonp(verify_response.text)
    (cache / "verify.jsonp").write_text(verify_response.text, encoding="utf-8")
    save_json(cache / "verify.json", verify_json)
    save_json(cache / "verify_request.json", {"url": verify_response.url, "params": verify_params})

    seccode = verify_json.get("data", {}).get("seccode") or {}
    demo_json = None
    if args.demo_login and verify_json.get("data", {}).get("result") == "success":
        demo_response = session.get(
            DEMO_LOGIN_URL,
            params={**seccode, "captcha_id": args.captcha_id},
            timeout=30,
        )
        demo_response.raise_for_status()
        demo_json = demo_response.json()
        save_json(cache / "demo_login.json", demo_json)

    summary = {
        "runtime": "pure-python",
        "cache": str(cache.resolve()),
        "lot_number": data["lot_number"],
        "captcha_type": data.get("captcha_type"),
        "biht": biht,
        "fixed_fields": fixed_fields,
        "lot_rules": lot_rules,
        "w_payload_keys": list(w_payload.keys()),
        "w_length": len(w),
        "status": verify_json.get("status"),
        "result": verify_json.get("data", {}).get("result"),
        "fail_count": verify_json.get("data", {}).get("fail_count"),
        "seccode": seccode,
        "demo_login": demo_json,
    }
    save_json(cache / "summary.json", summary)
    return summary, cache


def main() -> int:
    parser = argparse.ArgumentParser(description="Pure Python replay for Geetest GT4 risk_type=ai")
    parser.add_argument("--captcha-id", default=DEFAULT_CAPTCHA_ID)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=Path.cwd() / "js_reverse_cache" / "ai_runs")
    parser.add_argument("--captcha-user", help="captcha_v4_user cookie value; random 32-hex if omitted")
    parser.add_argument("--challenge", help="optional /load challenge UUID; random UUID if omitted")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--demo-login", action="store_true", help="also replay the demo /demo/login gate after verify success")
    parser.add_argument("--use-env-proxy", action="store_true")
    parser.add_argument(
        "--user-agent",
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
    )
    parser.add_argument(
        "--sec-ch-ua",
        default='"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    )
    args = parser.parse_args()

    if not args.bundle.exists():
        raise FileNotFoundError(f"Bundle not found: {args.bundle}")

    summaries = []
    for _ in range(args.rounds):
        summary, _cache = replay_once(args)
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    ok = all(item.get("status") == "success" and item.get("result") == "success" for item in summaries)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
