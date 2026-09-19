import json
import random
import time
from pathlib import Path
from urllib.parse import urljoin

import ddddocr
import requests
from PIL import Image, ImageDraw

from gt4_word_pure import (
    EM,
    GEE_GUARD,
    LOAD_URL,
    STATIC_BASE,
    VERIFY_URL,
    build_ocr_engines,
    build_session,
    calculate_biht,
    callback,
    encrypt_w,
    extract_bundle_metadata,
    parse_jsonp,
    prepare_ques_image,
    resolve_lot_fields,
    solve_pow,
    solve_word_reference,
)

ROOT = Path(__file__).resolve().parent
CID = "54088bb07d2df3c46b79f80300b0abbe"
CAPTCHA_USER = "713718b9d7784360a33f32736e593880"


def load_word_challenge(session):
    load_response = session.get(
        LOAD_URL,
        params={
            "callback": callback(),
            "captcha_id": CID,
            "client_type": "web",
            "risk_type": "word",
            "pt": 1,
            "lang": "zho",
        },
        timeout=30,
    )
    load_json = parse_jsonp(load_response.text)
    data = load_json["data"]
    if data.get("captcha_type") != "word":
        raise RuntimeError(f"unexpected type: {data.get('captcha_type')}")
    bg = session.get(urljoin(STATIC_BASE, data["imgs"]), timeout=30).content
    prompts = [
        session.get(urljoin(STATIC_BASE, path), timeout=30).content
        for path in data.get("ques") or []
    ]
    return data, bg, prompts, load_json


def one(session, fixed, rules, tag, classifier, max_resample=3, save_debug=False):
    attempts = []
    gct_cache = {}
    for attempt in range(1, max_resample + 1):
        data, bg, prompts, load_json = load_word_challenge(session)
        lot = data["lot_number"]
        try:
            solved = solve_word_reference(
                bg,
                prompts,
                classifier=classifier,
                require_high_confidence=True,
                min_sift_score=4,
            )
        except Exception as exc:
            attempts.append({"lot": lot, "error": str(exc), "attempt": attempt})
            continue

        methods = solved["methods"]
        exact_count = sum(1 for method in methods if method == "ocr-exact")
        # Prefer challenges where all prompts lock by OCR exact match.
        if exact_count < len(methods) and attempt < max_resample:
            attempts.append(
                {
                    "lot": lot,
                    "methods": methods,
                    "attempt": attempt,
                    "action": "resample",
                }
            )
            continue

        userresponse = solved["points"]
        passtime = random.randint(900, 1300)
        gct_path = data["gct_path"]
        if gct_path not in gct_cache:
            gct_cache[gct_path] = session.get(urljoin(STATIC_BASE, gct_path), timeout=30).text
        biht = calculate_biht(gct_cache[gct_path])
        pow_data = solve_pow(CID, lot, data["pow_detail"])
        payload = {
            "passtime": passtime,
            "userresponse": userresponse,
            "device_id": "",
            "lot_number": lot,
            **pow_data,
            "geetest": "captcha",
            "lang": "zh",
            "ep": "123",
            "biht": biht,
            "gee_guard": GEE_GUARD,
            **fixed,
            **resolve_lot_fields(lot, rules),
            "em": EM,
        }
        w, compact = encrypt_w(payload, str(data["pt"]))
        # Keep a little real wait without always sleeping full passtime.
        time.sleep(min(0.9, passtime / 1000))
        verify_response = session.get(
            VERIFY_URL,
            params={
                "callback": callback(),
                "captcha_id": CID,
                "client_type": "web",
                "lot_number": lot,
                "risk_type": data["captcha_type"],
                "payload": data["payload"],
                "process_token": data["process_token"],
                "payload_protocol": data["payload_protocol"],
                "pt": data["pt"],
                "w": w,
            },
            timeout=30,
        )
        verify_json = parse_jsonp(verify_response.text)
        result = (verify_json.get("data") or {}).get("result")
        summary = {
            "tag": tag,
            "lot": lot,
            "ques": solved["prompt_text"],
            "methods": methods,
            "exact_count": exact_count,
            "attempts": attempts,
            "userresponse": userresponse,
            "passtime": passtime,
            "w_length": len(w),
            "result": result,
            "fail_count": (verify_json.get("data") or {}).get("fail_count"),
            "matcher": "reference-sift-fast",
        }
        if save_debug:
            cache = ROOT / "js_reverse_cache" / "auto_int" / f"{tag}_{lot}"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "load.json").write_text(
                json.dumps(load_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (cache / "bg.jpg").write_bytes(bg)
            for index, ques_bytes in enumerate(prompts):
                (cache / f"ques_{index}.png").write_bytes(ques_bytes)
            summary["match"] = solved["match"]
            summary["compact"] = compact
            (cache / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (cache / "verify.json").write_text(
                json.dumps(verify_json, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(json.dumps(summary, ensure_ascii=False))
        return result == "success"

    print(json.dumps({"tag": tag, "result": "skipped", "attempts": attempts}, ensure_ascii=False))
    return False


def main():
    fixed, rules = extract_bundle_metadata(ROOT / "js_reverse_cache" / "gcaptcha4.js")
    session = build_session(False, captcha_user=CAPTCHA_USER)
    classifier = build_ocr_engines()
    ok = 0
    rounds = 8
    started = time.perf_counter()
    for index in range(rounds):
        if one(
            session,
            fixed,
            rules,
            f"r{index}",
            classifier=classifier,
            max_resample=3,
            save_debug=False,
        ):
            ok += 1
    elapsed = round(time.perf_counter() - started, 2)
    print(
        json.dumps(
            {
                "passed": ok,
                "rounds": rounds,
                "elapsed_sec": elapsed,
                "avg_sec": round(elapsed / max(rounds, 1), 2),
                "ddddocr": "1.6.1",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
