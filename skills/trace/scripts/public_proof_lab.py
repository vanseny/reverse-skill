#!/usr/bin/env python3
"""Deterministic public-safe protocol proof exercises."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zlib


EXACT_BODY = b"page=1&empty=&name=alpha%20beta"
SECRET = b"trace-public-lab"
PATH_VALUE = "/api/list"
NOW_VALUE = "1700000000123"
PAGE_VALUE = "1"
DECODE_DOCUMENT = {"anchor": "decode-chain-accepted", "items": [1, 2, 3]}


def compact_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def exact_wire_sample(correct: bool = True) -> dict[str, object]:
    body = EXACT_BODY if correct else b"empty=&name=alpha%20beta&page=1"
    signature = hashlib.sha256(b"POST\n/api/exact\n" + EXACT_BODY).hexdigest()
    headers = {"X-Body-Sign": signature if correct else hashlib.sha256(body).hexdigest()}
    accepted = body == EXACT_BODY and headers["X-Body-Sign"] == signature
    return {"accepted": accepted, "body": body.decode(), "headers": headers}


def rotate_left(value: int, bits: int) -> int:
    bits %= 32
    value &= 0xFFFFFFFF
    return ((value << bits) | (value >> (32 - bits))) & 0xFFFFFFFF if bits else value


def modded_digest(path: str = PATH_VALUE, now: str = NOW_VALUE, page: str = PAGE_VALUE, broken: bool = False) -> str:
    seed = f"{path}|{now}|{page}".encode("utf-8") + SECRET
    digest = hashlib.sha256(seed).digest()
    words = [int.from_bytes(digest[i:i + 4], "big") for i in range(0, 16, 4)]
    mixed = 0
    for index, word in enumerate(words):
        rotated = rotate_left(word, index * 7)
        mixed = (mixed ^ rotated) & (0xFFFFFFFF if not broken else 0xFFFFFFFFFFFFFFFF)
    return f"{mixed:08x}" + hashlib.sha256(seed + str(mixed).encode()).hexdigest()[:16]


def decode_payload(payload: bytes) -> dict[str, object]:
    prefix = b"LAB1."
    if not payload.startswith(prefix):
        raise ValueError("missing LAB1 prefix")
    compressed = base64.urlsafe_b64decode(payload[len(prefix):])
    return json.loads(zlib.decompress(compressed).decode("utf-8"))


def encoded_payload() -> bytes:
    return b"LAB1." + base64.urlsafe_b64encode(zlib.compress(compact_json(DECODE_DOCUMENT)))


def self_test() -> None:
    ok = exact_wire_sample(True)
    bad_wire = exact_wire_sample(False)
    good_digest = modded_digest()
    bad_digest = hashlib.sha256(f"{PATH_VALUE}|{NOW_VALUE}|{PAGE_VALUE}".encode()).hexdigest()[:24]
    decoded = decode_payload(encoded_payload())
    assert ok["accepted"] is True
    assert bad_wire["accepted"] is False
    assert good_digest != bad_digest
    assert decoded["anchor"] == "decode-chain-accepted"
    print("public_proof_lab_self_test=PASS cases=3 negative_controls=2")


def emit_fixtures() -> None:
    payload = {
        "exact_wire_correct": exact_wire_sample(True),
        "exact_wire_wrong_order": exact_wire_sample(False),
        "modded_digest": {
            "input": {"path": PATH_VALUE, "now": NOW_VALUE, "page": PAGE_VALUE},
            "expected": modded_digest(),
            "broken_standard_shape": hashlib.sha256(f"{PATH_VALUE}|{NOW_VALUE}|{PAGE_VALUE}".encode()).hexdigest()[:24],
        },
        "decode_payload": {
            "encoded": encoded_payload().decode("ascii"),
            "decoded": DECODE_DOCUMENT,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run public-safe Trace proof exercises.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--emit-fixtures", action="store_true")
    args = parser.parse_args()
    if args.emit_fixtures:
        emit_fixtures()
        return
    self_test()


if __name__ == "__main__":
    main()
