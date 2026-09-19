import argparse
import hashlib
import io
import json
import random
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urljoin

import cv2
import ddddocr
import numpy as np
import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from scipy.optimize import linear_sum_assignment

LOAD_URL = "https://gcaptcha4.geetest.com/load"
VERIFY_URL = "https://gcaptcha4.geetest.com/verify"
STATIC_BASE = "https://static.geetest.com/"
RSA_N_HEX = (
    "c1e3934d1614465b33053e7f48ee4ec87b14b95ef88947713d25eecbff7e74c"
    "7977d02dc1d9451f79dd5d1c10c29acb6a9b4d6fb7d0a0279b6719e1772565f"
    "09af627715919221aef91899cae08c0d686d748b20a3603be2318ca6bc2b597"
    "06592a9219d0bf05c9f65023a21d2330807252ae0066d59ceefa5f2748ea80bab81"
)
RSA_E = 65537
GEE_GUARD = {
    "roe": {
        "aup": "3", "sep": "3", "egp": "3", "auh": "3",
        "rew": "3", "snh": "3", "res": "3", "cdc": "3",
    },
}
EM = {"ph": 0, "cp": 0, "ek": "11", "wd": 1, "nt": 0, "si": 0, "sc": 0}
CAPTCHA_ID_DEMO = "54088bb07d2df3c46b79f80300b0abbe"


def callback():
    return f"geetest_{int(time.time() * 1000)}"


def parse_jsonp(text):
    match = re.fullmatch(r"\s*[^(]+\((.*)\)\s*;?\s*", text, re.S)
    if not match:
        raise ValueError(f"Invalid JSONP: {text[:160]}")
    return json.loads(match.group(1))


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def decode_uri_bytes(value):
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


def decode_string_table(source):
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


def extract_bundle_metadata(bundle_path):
    source = bundle_path.read_text(encoding="utf-8")
    strings = decode_string_table(source)
    lot_match = re.search(r'["\'](n\[[^"\']+)["\']\s*:\s*[^\n]*?\((\d+)\)', source)
    region_start = max(0, lot_match.start() - 3000) if lot_match else 0
    metadata_region = source[region_start:lot_match.end() + 500] if lot_match else ""
    fixed_match = re.search(
        r'\]\s*=\s*\{\s*([A-Za-z_$][A-Za-z0-9_$]*):\s*[^\n]*?\((\d+)\)\s*\}',
        metadata_region,
    )
    if not fixed_match or not lot_match:
        raise ValueError("Current bundle metadata initialization was not recognized")
    return (
        {fixed_match.group(1): strings[int(fixed_match.group(2))]},
        {lot_match.group(1): strings[int(lot_match.group(2))]},
    )


def resolve_lot_expression(expression, lot_number):
    def replace(match):
        start, end = map(int, match.groups())
        return lot_number[start:end + 1]

    return re.sub(r"n\[(\d+):(\d+)\]", replace, expression).replace("+", "")


def resolve_lot_fields(lot_number, rules):
    result = {}
    for key_expression, value_expression in rules.items():
        path = resolve_lot_expression(key_expression, lot_number).split(".")
        value = resolve_lot_expression(value_expression, lot_number)
        target = result
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = value
    return result


def extract_function(source, start):
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


def int32(value):
    value &= 0xFFFFFFFF
    return value if value < 0x80000000 else value - 0x100000000


def js_5381_hash(value):
    state = 5381
    utf16 = value.encode("utf-16-le", "surrogatepass")
    for index in range(0, len(utf16), 2):
        code_unit = int.from_bytes(utf16[index:index + 2], "little")
        state = int32(state) * 33 + code_unit
    return int32(state) & 0x7FFFFFFF


def calculate_biht(gct_source):
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


def solve_pow(captcha_id, lot_number, detail):
    hashfunc = detail["hashfunc"].lower()
    if hashfunc != "sha256":
        raise ValueError(f"Unsupported PoW hash: {hashfunc}")
    prefix = "|".join([
        str(detail["version"]), str(detail["bits"]), hashfunc,
        detail["datetime"], captcha_id, lot_number, "",
    ]) + "|"
    target = 1 << (256 - int(detail["bits"]))
    while True:
        message = prefix + secrets.token_hex(8)
        digest = hashlib.sha256(message.encode()).hexdigest()
        if int(digest, 16) < target:
            return {"pow_msg": message, "pow_sign": digest}


def encrypt_w(payload, pt):
    compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if str(pt) != "1":
        raise ValueError(f"Pure Python implementation supports pt=1, got {pt}")
    aes_key = secrets.token_hex(8).encode()
    aes_hex = AES.new(aes_key, AES.MODE_CBC, b"0000000000000000").encrypt(
        pad(compact.encode(), AES.block_size)
    ).hex()
    public_key = RSA.construct((int(RSA_N_HEX, 16), RSA_E))
    rsa_hex = PKCS1_v1_5.new(public_key).encrypt(aes_key).hex()
    return aes_hex + rsa_hex, compact


def download(session, url):
    response = session.get(urljoin(STATIC_BASE, url), timeout=30)
    response.raise_for_status()
    return response


def image_to_png_bytes(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _ocr_vote(classifiers, images):
    if not isinstance(classifiers, (list, tuple)):
        classifiers = [classifiers]
    votes = {}
    for classifier in classifiers:
        for image in images:
            try:
                text = (classifier.classification(image_to_png_bytes(image)) or "").strip()
            except Exception:
                text = ""
            if not text:
                continue
            # Prefer single Chinese glyph outputs.
            score = 2 if len(text) == 1 else 1
            votes[text] = votes.get(text, 0) + score
    if not votes:
        return ""
    return sorted(votes.items(), key=lambda item: (-item[1], -len(item[0])))[0][0]


_OCR_ENGINE_CACHE = None
_DET_ENGINE_CACHE = None


def build_ocr_engines():
    """ddddocr 1.6.x: default + beta vote is more stable on GT4 colorful glyphs."""
    global _OCR_ENGINE_CACHE
    if _OCR_ENGINE_CACHE is not None:
        return _OCR_ENGINE_CACHE
    default = ddddocr.DdddOcr(show_ad=False)
    try:
        beta = ddddocr.DdddOcr(show_ad=False, beta=True)
        _OCR_ENGINE_CACHE = [default, beta]
    except Exception:
        _OCR_ENGINE_CACHE = [default]
    return _OCR_ENGINE_CACHE


def build_detector():
    global _DET_ENGINE_CACHE
    if _DET_ENGINE_CACHE is None:
        _DET_ENGINE_CACHE = ddddocr.DdddOcr(ocr=False, det=True, show_ad=False)
    return _DET_ENGINE_CACHE


def classify_image(classifier, image):
    engines = classifier if isinstance(classifier, list) else [classifier]
    rgb = image.convert("RGB")
    gray = rgb.convert("L")
    variants = [
        rgb,
        ImageOps.autocontrast(rgb),
        ImageEnhance.Contrast(rgb).enhance(2.0),
        ImageEnhance.Contrast(rgb).enhance(3.0),
        ImageEnhance.Sharpness(ImageEnhance.Contrast(rgb).enhance(2.0)).enhance(2.0),
        gray.convert("RGB"),
        ImageOps.autocontrast(gray).convert("RGB"),
        ImageOps.invert(gray).convert("RGB"),
        ImageOps.expand(rgb, border=8, fill="white"),
        ImageOps.expand(ImageOps.invert(gray), border=8, fill="white").convert("RGB"),
        rgb.resize((max(1, rgb.width * 2), max(1, rgb.height * 2)), Image.Resampling.LANCZOS),
        ImageOps.autocontrast(gray).resize(
            (max(1, rgb.width * 2), max(1, rgb.height * 2)), Image.Resampling.LANCZOS
        ).convert("RGB"),
    ]
    return _ocr_vote(engines, variants)


def classify_bg_crop(classifier, crop_bgr):
    """OCR colorful GT4 glyph by converting high-chroma strokes to black-on-white."""
    if crop_bgr is None or getattr(crop_bgr, "size", 0) == 0:
        return ""
    engines = classifier if isinstance(classifier, list) else [classifier]
    mask = _bg_color_mask(crop_bgr)
    # thicken thin neon strokes a bit for OCR
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    thick = cv2.dilate(mask, kernel, iterations=1)
    images = []
    for stroke in (mask, thick):
        for invert in (False, True):
            canvas = np.full(stroke.shape, 255 if not invert else 0, dtype=np.uint8)
            canvas[stroke > 0] = 0 if not invert else 255
            canvas = cv2.copyMakeBorder(
                canvas,
                10,
                10,
                10,
                10,
                cv2.BORDER_CONSTANT,
                value=(255 if not invert else 0),
            )
            for scale in (1.0, 1.6, 2.2):
                scaled = cv2.resize(
                    canvas,
                    None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_CUBIC,
                )
                images.append(Image.fromarray(scaled).convert("RGB"))
    # Also try raw colorful crop variants.
    raw = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
    images.extend([
        raw,
        ImageOps.autocontrast(raw),
        ImageEnhance.Contrast(raw).enhance(2.2),
        ImageEnhance.Contrast(raw).enhance(3.2),
        ImageOps.expand(raw, border=8, fill="white"),
        raw.resize((max(1, raw.width * 2), max(1, raw.height * 2)), Image.Resampling.LANCZOS),
        ImageOps.autocontrast(raw.convert("L")).convert("RGB"),
        ImageOps.invert(raw.convert("L")).convert("RGB"),
    ])
    return _ocr_vote(engines, images)


def prepare_ques_image(raw_bytes):
    image = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.alpha_composite(image)
    return canvas.convert("RGB")


def first_cjk(value):
    return next((char for char in str(value or "") if "\u3400" <= char <= "\u9fff"), "")


def prompt_rgba(raw_bytes):
    return Image.open(io.BytesIO(raw_bytes)).convert("RGBA")


def classify_prompt_text(classifier, raw_bytes):
    """Reference high-accuracy prompt OCR from 文字点选/main.py."""
    engines = classifier if isinstance(classifier, list) else [classifier]
    # Reference order: beta first, then classic.
    ordered = list(engines)
    if len(ordered) >= 2:
        # build_ocr_engines returns [default, beta]; reverse for prompt.
        ordered = [ordered[-1], ordered[0]]
    image = prompt_rgba(raw_bytes)
    white = Image.new("RGBA", image.size, "white")
    white.alpha_composite(image)
    normalized = ImageOps.autocontrast(white.convert("L")).resize((128, 128))
    payload = image_to_png_bytes(normalized.convert("RGB"))
    for engine in ordered:
        label = first_cjk(engine.classification(payload))
        if label:
            return label
    # Fallbacks only if reference path fails.
    if "A" in image.getbands():
        alt = ImageOps.autocontrast(ImageOps.invert(image.getchannel("A"))).resize((128, 128))
        payload = image_to_png_bytes(alt.convert("RGB"))
        for engine in ordered:
            label = first_cjk(engine.classification(payload))
            if label:
                return label
    return first_cjk(classify_image(classifier, prepare_ques_image(raw_bytes)))


def candidate_labels(crop, classifier, fast=True):
    """Multi-angle OCR on raw crop and high-chroma mask.

    fast=True keeps only the high-yield angles used by the reference path,
    which is enough for exact locking and much cheaper than dense sampling.
    """
    engines = classifier if isinstance(classifier, list) else [classifier]
    # Prefer beta first when available.
    if len(engines) >= 2:
        engines = [engines[-1], engines[0]]
    labels = set()
    rgb = np.array(crop.convert("RGB"))
    masks = [
        crop,
        Image.fromarray(np.where((rgb.max(axis=2) - rgb.min(axis=2)) > 80, 0, 255).astype(np.uint8)),
    ]
    angles = range(-40, 41, 10) if fast else range(-45, 46, 5)
    for image in masks:
        for angle in angles:
            rotated = image.rotate(angle, expand=True, fillcolor="white").resize((96, 96))
            payload = image_to_png_bytes(rotated.convert("RGB"))
            for engine in engines:
                label = first_cjk(engine.classification(payload))
                if label:
                    labels.add(label)
    return labels


def feature_score(prompt, candidate):
    create_sift = getattr(cv2, "SIFT_create", None)
    if create_sift is None:
        return 0
    if "A" in prompt.getbands():
        prompt_gray = np.array(ImageOps.invert(prompt.getchannel("A")).resize((128, 128)))
    else:
        prompt_gray = np.array(ImageOps.autocontrast(prompt.convert("L")).resize((128, 128)))
    candidate_gray = cv2.cvtColor(
        np.array(candidate.convert("RGB").resize((128, 128))), cv2.COLOR_RGB2GRAY
    )
    sift = create_sift()
    _, prompt_descriptors = sift.detectAndCompute(prompt_gray, None)
    _, candidate_descriptors = sift.detectAndCompute(candidate_gray, None)
    if prompt_descriptors is None or candidate_descriptors is None:
        return 0
    pairs = cv2.BFMatcher().knnMatch(prompt_descriptors, candidate_descriptors, k=2)
    return sum(
        1
        for pair in pairs
        if len(pair) == 2 and pair[0].distance < 0.8 * pair[1].distance
    )


def glyph_left_score(prompt, labels, font_path=r"C:\Windows\Fonts\msyh.ttc"):
    font_file = Path(font_path)
    if not font_file.exists() or not labels:
        return 0
    if "A" in prompt.getbands():
        left = np.array(ImageOps.invert(prompt.getchannel("A")).resize((128, 128)))[:, :58]
    else:
        left = np.array(ImageOps.autocontrast(prompt.convert("L")).resize((128, 128)))[:, :58]
    font = ImageFont.truetype(str(font_file), 86)
    best = 0
    create_sift = getattr(cv2, "SIFT_create", None)
    if create_sift is None:
        return 0
    sift = create_sift()
    for label in labels:
        canvas = Image.new("L", (128, 128), "white")
        draw = ImageDraw.Draw(canvas)
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(
            ((128 - (box[2] - box[0])) / 2, (128 - (box[3] - box[1])) / 2 - box[1]),
            label,
            font=font,
            fill="black",
        )
        right = np.array(ImageOps.invert(canvas))[:, :58]
        _, left_desc = sift.detectAndCompute(left, None)
        _, right_desc = sift.detectAndCompute(right, None)
        if left_desc is None or right_desc is None:
            continue
        pairs = cv2.BFMatcher().knnMatch(left_desc, right_desc, k=2)
        best = max(
            best,
            sum(
                1
                for pair in pairs
                if len(pair) == 2 and pair[0].distance < 0.8 * pair[1].distance
            ),
        )
    return best


def solve_word_reference(
    background_bytes,
    prompt_bytes_list,
    classifier=None,
    require_high_confidence=False,
    min_sift_score=4,
):
    """Port of the high-success reference matcher from 文字点选/main.py."""
    engines = classifier if isinstance(classifier, list) else None
    if engines is None:
        engines = build_ocr_engines()
    # Keep [default, beta] storage, but reference prompt prefers beta.
    default_ocr = engines[0]
    beta_ocr = engines[1] if len(engines) > 1 else engines[0]
    detector = build_detector()

    prompt_images = [prompt_rgba(data) for data in prompt_bytes_list]
    prompt_text = []
    for raw in prompt_bytes_list:
        label = classify_prompt_text([default_ocr, beta_ocr], raw)
        if not label:
            raise RuntimeError("prompt OCR failed")
        prompt_text.append(label)

    boxes = [list(map(int, box)) for box in detector.detection(background_bytes)]
    # Keep only reasonable glyph boxes.
    filtered = []
    for box in boxes:
        x1, y1, x2, y2 = box
        width, height = x2 - x1, y2 - y1
        if width < 18 or height < 18 or width > 120 or height > 120:
            continue
        if width / max(height, 1) > 3.5 or height / max(width, 1) > 3.5:
            continue
        filtered.append(box)
    boxes = filtered or boxes
    if len(boxes) < len(prompt_bytes_list):
        raise RuntimeError(f"only detected {len(boxes)} candidate boxes")

    image = Image.open(io.BytesIO(background_bytes)).convert("RGB")
    crops = [
        image.crop(
            (
                max(0, x1 - 4),
                max(0, y1 - 4),
                min(image.width, x2 + 4),
                min(image.height, y2 + 4),
            )
        )
        for x1, y1, x2, y2 in boxes
    ]
    labels = [candidate_labels(crop, [beta_ocr, default_ocr], fast=True) for crop in crops]

    selected = {}
    used = set()
    methods = []
    for prompt_index, label in enumerate(prompt_text):
        exact = [i for i, values in enumerate(labels) if i not in used and label in values]
        if len(exact) == 1:
            selected[prompt_index] = exact[0]
            used.add(exact[0])

    # Fast path: when every prompt is uniquely locked by OCR, skip SIFT/radical.
    if len(selected) == len(prompt_images):
        methods = ["ocr-exact"] * len(prompt_images)
    else:
        for prompt_index, prompt in enumerate(prompt_images):
            if prompt_index in selected:
                methods.append("ocr-exact")
                continue
            if require_high_confidence:
                # Prefer resampling a fresh challenge over expensive low-confidence matching.
                raise RuntimeError("not all prompts locked by ocr-exact")
            scores = {
                i: feature_score(prompt, crop)
                for i, crop in enumerate(crops)
                if i not in used
            }
            if not scores:
                raise RuntimeError("no remaining candidates")
            if max(scores.values()) <= 1:
                radical_scores = {i: glyph_left_score(prompt, labels[i]) for i in scores}
                ranked = sorted(
                    radical_scores,
                    key=lambda i: (radical_scores[i], scores[i], -i),
                    reverse=True,
                )
                candidate = ranked[0]
                if radical_scores[candidate] <= 0 or (
                    len(ranked) > 1 and radical_scores[ranked[0]] == radical_scores[ranked[1]]
                ):
                    partial = [
                        i for i in scores
                        if prompt_text[prompt_index] and any(
                            prompt_text[prompt_index] in value or value in prompt_text[prompt_index]
                            for value in labels[i]
                        )
                    ]
                    if len(partial) == 1:
                        candidate = partial[0]
                        method = "text-partial"
                    else:
                        candidate = max(scores, key=lambda i: (scores[i], radical_scores[i], -i))
                        method = f"lowconf-{scores[candidate]}-{radical_scores[candidate]}"
                else:
                    method = f"radical-{radical_scores[candidate]}"
            else:
                candidate = max(scores, key=lambda i: (scores[i], -i))
                method = f"sift-{scores[candidate]}"
                if scores[candidate] < min_sift_score:
                    raise RuntimeError(f"low sift confidence: {scores[candidate]}")
            selected[prompt_index] = candidate
            used.add(candidate)
            methods.append(method)

    points = []
    centers = []
    match = []
    for prompt_index in range(len(prompt_bytes_list)):
        box = boxes[selected[prompt_index]]
        x1, y1, x2, y2 = box
        center = [(x1 + x2) / 2, (y1 + y2) / 2]
        centers.append(center)
        points.append(
            [
                round(center[0] / image.width * 10000),
                round(center[1] / image.height * 10000),
            ]
        )
        match.append(
            {
                "ques": prompt_text[prompt_index],
                "matched": ",".join(sorted(labels[selected[prompt_index]])),
                "method": methods[prompt_index],
                "center": center,
                "box": box,
                "bg_index": selected[prompt_index],
                "ques_index": prompt_index,
            }
        )
    return {
        "points": points,
        "centers": centers,
        "prompt_text": prompt_text,
        "methods": methods,
        "match": match,
        "boxes": boxes,
        "width": image.width,
        "height": image.height,
    }


def _cv_image(raw_bytes):
    return cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)


def _ques_ink_from_bytes(raw_bytes):
    image = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("Failed to decode ques image")
    if image.ndim == 2:
        ink = (image < 200).astype(np.uint8) * 255
    elif image.shape[2] == 4:
        alpha = image[:, :, 3]
        gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
        ink = ((gray < 200) & (alpha > 10)).astype(np.uint8) * 255
        if int(ink.sum()) < 50:
            ink = (alpha > 10).astype(np.uint8) * 255
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ink = (gray < 200).astype(np.uint8) * 255
    ys, xs = np.where(ink > 0)
    if len(xs) == 0:
        return np.zeros((16, 16), dtype=np.uint8)
    return ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _bg_color_mask(crop_bgr):
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    chroma = cv2.inRange(hsv, (0, 35, 35), (180, 255, 255))
    blue, green, red = cv2.split(crop_bgr)
    spread = (
        np.maximum(np.maximum(red, green), blue).astype(np.int16)
        - np.minimum(np.minimum(red, green), blue).astype(np.int16)
    )
    chroma2 = (spread > 28).astype(np.uint8) * 255
    mask = cv2.bitwise_or(chroma, chroma2)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask


def _normalize_binary(mask, size=64):
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return np.zeros((size, size), dtype=np.uint8)
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    height, width = crop.shape
    side = max(height, width)
    canvas = np.zeros((side, side), dtype=np.uint8)
    y0 = (side - height) // 2
    x0 = (side - width) // 2
    canvas[y0:y0 + height, x0:x0 + width] = crop
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)


def _template_score(template, image):
    if template.size == 0 or image.size == 0:
        return -1.0
    best = -1.0
    image_h, image_w = image.shape[:2]
    template_h, template_w = template.shape[:2]
    if template_h < 4 or template_w < 4 or image_h < 8 or image_w < 8:
        return -1.0
    base = min(image_h, image_w) / max(template_h, template_w)
    image_edge = cv2.Canny(image, 50, 150)
    for scale in np.linspace(max(0.3, base * 0.45), base * 1.35, 28):
        height = max(8, int(template_h * scale))
        width = max(8, int(template_w * scale))
        if height >= image_h or width >= image_w:
            continue
        resized = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
        resized = (resized > 80).astype(np.uint8) * 255
        for rotation in (
            None,
            cv2.ROTATE_90_CLOCKWISE,
            cv2.ROTATE_180,
            cv2.ROTATE_90_COUNTERCLOCKWISE,
        ):
            candidate = resized if rotation is None else cv2.rotate(resized, rotation)
            if candidate.shape[0] >= image_h or candidate.shape[1] >= image_w:
                continue
            response = cv2.matchTemplate(image, candidate, cv2.TM_CCOEFF_NORMED)
            if response.size:
                best = max(best, float(response.max()))
            template_edge = cv2.Canny(candidate, 50, 150)
            if template_edge.sum() > 0 and image_edge.sum() > 0:
                edge_response = cv2.matchTemplate(
                    image_edge, template_edge, cv2.TM_CCOEFF_NORMED
                )
                if edge_response.size:
                    best = max(best, float(edge_response.max()))
    return best


def _projection_score(left, right):
    def project(mask):
        binary = (mask > 80).astype(np.float32)
        x_hist = binary.sum(axis=0)
        y_hist = binary.sum(axis=1)
        x_hist = cv2.resize(x_hist.reshape(1, -1), (32, 1)).flatten()
        y_hist = cv2.resize(y_hist.reshape(1, -1), (32, 1)).flatten()
        x_hist = x_hist / (np.linalg.norm(x_hist) + 1e-6)
        y_hist = y_hist / (np.linalg.norm(y_hist) + 1e-6)
        return x_hist, y_hist

    left_x, left_y = project(left)
    right_x, right_y = project(right)
    return float((left_x @ right_x + left_y @ right_y) / 2)


def _dice(left, right):
    left_bin = left > 80
    right_bin = right > 80
    inter = np.logical_and(left_bin, right_bin).sum()
    return float(2 * inter / (left_bin.sum() + right_bin.sum() + 1e-9))


def score_ques_against_box(ques_raw_bytes, bg_bgr, box):
    x1, y1, x2, y2 = [int(value) for value in box]
    crop = bg_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return -10.0, {"template": -1.0, "projection": 0.0, "dice": 0.0}
    ques_ink = _ques_ink_from_bytes(ques_raw_bytes)
    bg_mask = _bg_color_mask(crop)
    padded = cv2.copyMakeBorder(bg_mask, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=0)
    template = _template_score(ques_ink, padded)
    ques_norm = _normalize_binary(ques_ink)
    bg_norm = _normalize_binary(bg_mask)
    # also score 180-degree silhouette alignment
    dice = max(_dice(ques_norm, bg_norm), _dice(cv2.rotate(ques_norm, cv2.ROTATE_180), bg_norm))
    projection = max(
        _projection_score(ques_norm, bg_norm),
        _projection_score(cv2.rotate(ques_norm, cv2.ROTATE_180), bg_norm),
    )
    score = template * 3.5 + projection * 1.2 + dice * 0.8
    return score, {
        "template": template,
        "projection": projection,
        "dice": dice,
    }


def detect_chars(detector, classifier, bg_bytes):
    boxes = detector.detection(bg_bytes) or []
    image = Image.open(io.BytesIO(bg_bytes)).convert("RGB")
    bg_bgr = _cv_image(bg_bytes)
    chars = []
    for box in boxes:
        x1, y1, x2, y2 = [int(v) for v in box]
        width = x2 - x1
        height = y2 - y1
        if width < 18 or height < 18:
            continue
        if width > 120 or height > 120:
            continue
        # Drop ultra-flat false boxes on image borders.
        if width / max(height, 1) > 3.5 or height / max(width, 1) > 3.5:
            continue
        crop = image.crop((x1, y1, x2, y2))
        crop_bgr = bg_bgr[y1:y2, x1:x2].copy()
        # Vote across colorful crop variants and black-on-white stroke renders.
        text_a = classify_image(classifier, crop)
        text_b = classify_bg_crop(classifier, crop_bgr)
        if text_a and text_b:
            text = text_a if text_a == text_b or len(text_a) == 1 else (
                text_a if len(text_a) <= len(text_b) else text_b
            )
            # Prefer exact single-char agreement; otherwise keep first non-empty single char.
            if text_a == text_b:
                text = text_a
            elif len(text_a) == 1 and len(text_b) != 1:
                text = text_a
            elif len(text_b) == 1 and len(text_a) != 1:
                text = text_b
            else:
                text = text_a or text_b
        else:
            text = text_a or text_b
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        chars.append({
            "box": [x1, y1, x2, y2],
            "text": text,
            "center": [center_x, center_y],
            "crop": crop,
            "crop_bgr": crop_bgr,
        })
    return image, chars, bg_bgr


def _text_match_score(ques_text, bg_text):
    ques_text = (ques_text or "").strip()
    bg_text = (bg_text or "").strip()
    if not ques_text or not bg_text:
        return 0.0
    if ques_text == bg_text:
        return 8.0
    if ques_text in bg_text or bg_text in ques_text:
        return 5.0
    if set(ques_text) & set(bg_text):
        return 2.0
    return 0.0


def match_order(ques_items, bg_chars, bg_bgr=None):
    if not ques_items:
        raise RuntimeError("No ques images")
    if len(bg_chars) < len(ques_items):
        raise RuntimeError(
            f"Detected {len(bg_chars)} chars, need at least {len(ques_items)}"
        )

    score_matrix = np.zeros((len(ques_items), len(bg_chars)), dtype=np.float64)
    detail_matrix = [[None] * len(bg_chars) for _ in range(len(ques_items))]
    for ques_index, ques in enumerate(ques_items):
        ques_bytes = ques.get("raw_bytes")
        if ques_bytes is None:
            raise RuntimeError("ques item missing raw_bytes")
        ques_text = (ques.get("text") or "").strip()
        for bg_index, bg_char in enumerate(bg_chars):
            shape_score, detail = score_ques_against_box(
                ques_bytes,
                bg_bgr if bg_bgr is not None else bg_char["crop_bgr"],
                bg_char["box"],
            )
            text_score = _text_match_score(ques_text, bg_char.get("text"))
            # OCR agreement is primary after ddddocr 1.6.x; shape is fallback.
            total = text_score * 3.0 + shape_score
            # Strong exact-text prior for single Chinese glyphs.
            if text_score >= 8.0 and len(ques_text) == 1:
                total += 20.0
            score_matrix[ques_index, bg_index] = total
            detail_matrix[ques_index][bg_index] = {
                **detail,
                "text_score": text_score,
                "shape_score": shape_score,
                "total": total,
            }

    # First lock unique exact text matches, then Hungarian on remaining pairs.
    assigned_ques = {}
    used_bg = set()
    for ques_index, ques in enumerate(ques_items):
        ques_text = (ques.get("text") or "").strip()
        if len(ques_text) != 1:
            continue
        exact = [
            bg_index
            for bg_index, bg_char in enumerate(bg_chars)
            if (bg_char.get("text") or "").strip() == ques_text
        ]
        if len(exact) == 1 and exact[0] not in used_bg:
            assigned_ques[ques_index] = exact[0]
            used_bg.add(exact[0])

    remaining_ques = [i for i in range(len(ques_items)) if i not in assigned_ques]
    remaining_bg = [j for j in range(len(bg_chars)) if j not in used_bg]
    if remaining_ques and remaining_bg:
        sub = score_matrix[np.ix_(remaining_ques, remaining_bg)]
        row_indices, col_indices = linear_sum_assignment(-sub)
        for r, c in zip(row_indices.tolist(), col_indices.tolist()):
            assigned_ques[remaining_ques[r]] = remaining_bg[c]

    order = []
    for ques_index in range(len(ques_items)):
        bg_index = assigned_ques[ques_index]
        detail = detail_matrix[ques_index][bg_index] or {}
        order.append({
            "ques": ques_items[ques_index].get("text", ""),
            "matched": bg_chars[bg_index].get("text", ""),
            "score": float(score_matrix[ques_index, bg_index]),
            "text_score": float(detail.get("text_score", 0)),
            "shape_score": float(detail.get("shape_score", 0)),
            "template": float(detail.get("template", -1)),
            "projection": float(detail.get("projection", 0)),
            "dice": float(detail.get("dice", 0)),
            "center": bg_chars[bg_index]["center"],
            "box": bg_chars[bg_index]["box"],
            "bg_index": bg_index,
            "ques_index": ques_index,
            "locked_by_text": ques_index in {
                qi for qi, bj in assigned_ques.items()
                if _text_match_score(ques_items[qi].get("text"), bg_chars[bj].get("text")) >= 8
            },
        })
    return order


def encode_word_coord(value, size):
    # Browser word payload uses integer pairs:
    #   [round(x / width * 10000), round(y / height * 10000)]
    # Confirmed from paused $_BBFB assembly on gcaptcha4.js.
    return int(value * 10000 / size + 0.5)


def build_userresponse(centers, width, height, passtime=None):
    if not centers:
        raise ValueError("No click centers")
    # Word captcha does NOT attach per-click timestamps in userresponse.
    return [
        [encode_word_coord(x, width), encode_word_coord(y, height)]
        for x, y in centers
    ]


def build_session(use_env_proxy, captcha_user=None):
    session = requests.Session()
    session.trust_env = use_env_proxy
    session.headers.update({
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://gt4.geetest.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
    })
    # Browser keeps captcha_v4_user on gcaptcha4.geetest.com across rounds.
    if captcha_user:
        session.cookies.set(
            "captcha_v4_user",
            captcha_user,
            domain="gcaptcha4.geetest.com",
            path="/",
        )
    return session


def solve_once(session, captcha_id, fixed_fields, lot_rules, cache_root, manual_points=None, device_id=None):
    load_response = session.get(LOAD_URL, params={
        "callback": callback(),
        "captcha_id": captcha_id,
        "client_type": "web",
        "risk_type": "word",
        "pt": 1,
        "lang": "zho",
    }, timeout=30)
    load_response.raise_for_status()
    load_json = parse_jsonp(load_response.text)
    if load_json.get("status") != "success":
        raise RuntimeError(f"Load failed: {load_json}")
    data = load_json["data"]
    if data.get("captcha_type") != "word":
        raise RuntimeError(f"Expected word captcha, got {data.get('captcha_type')}")

    cache = cache_root / data["lot_number"]
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "load.jsonp").write_text(load_response.text, encoding="utf-8")
    save_json(cache / "load.json", load_json)
    save_json(cache / "cookies.json", requests.utils.dict_from_cookiejar(session.cookies))

    bg_response = download(session, data["imgs"])
    (cache / "bg.jpg").write_bytes(bg_response.content)
    classifier = build_ocr_engines()

    ques_items = []
    prompt_bytes_list = []
    for index, ques_path in enumerate(data.get("ques") or []):
        ques_response = download(session, ques_path)
        (cache / f"ques_{index}.png").write_bytes(ques_response.content)
        ques_image = prepare_ques_image(ques_response.content)
        ques_image.save(cache / f"ques_{index}_white.png")
        prompt_bytes_list.append(ques_response.content)
        ques_items.append({
            "index": index,
            "path": ques_path,
            "text": "",
            "image": ques_image,
            "raw_bytes": ques_response.content,
        })

    if manual_points:
        with Image.open(cache / "bg.jpg") as bg_image:
            bg_width, bg_height = bg_image.size
        centers = [list(map(float, point.split(","))) for point in manual_points]
        match_info = [{"manual": True, "center": center} for center in centers]
        userresponse = build_userresponse(centers, bg_width, bg_height)
    else:
        if not prompt_bytes_list:
            raise RuntimeError("Load response did not include ques images")
        # Prefer the high-success reference recognition pipeline.
        solved = solve_word_reference(
            bg_response.content, prompt_bytes_list, classifier=classifier
        )
        centers = solved["centers"]
        match_info = solved["match"]
        userresponse = solved["points"]
        for index, text in enumerate(solved["prompt_text"]):
            if index < len(ques_items):
                ques_items[index]["text"] = text
        with Image.open(cache / "bg.jpg") as bg_image:
            bg_width, bg_height = bg_image.size

    passtime = random.randint(900, 1400)

    gct_response = download(session, data["gct_path"])
    (cache / "gct.raw.js").write_text(gct_response.text, encoding="utf-8")
    biht = calculate_biht(gct_response.text)
    pow_data = solve_pow(captcha_id, data["lot_number"], data["pow_detail"])

    # Browser assembly always inserts device_id (often empty string) before lot_number.
    w_payload = {
        "passtime": passtime,
        "userresponse": userresponse,
        "device_id": device_id if device_id is not None else "",
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
    w, compact = encrypt_w(w_payload, str(data["pt"]))
    save_json(cache / "ocr.json", {
        "ques": [
            {"index": item["index"], "path": item["path"], "text": item["text"]}
            for item in ques_items
        ],
        "match": match_info,
        "userresponse": userresponse,
        "passtime": passtime,
        "bg_size": [bg_width, bg_height],
        "matcher": "reference-sift",
    })
    save_json(cache / "pure_output.json", {
        "w": w,
        "wPayload": w_payload,
        "compact": compact,
        "fixedFields": fixed_fields,
        "lotRules": lot_rules,
    })

    time.sleep(passtime / 1000)

    verify_response = session.get(VERIFY_URL, params={
        "callback": callback(),
        "captcha_id": captcha_id,
        "client_type": "web",
        "lot_number": data["lot_number"],
        "risk_type": data["captcha_type"],
        "payload": data["payload"],
        "process_token": data["process_token"],
        "payload_protocol": data["payload_protocol"],
        "pt": data["pt"],
        "w": w,
    }, timeout=30)
    verify_response.raise_for_status()
    verify_json = parse_jsonp(verify_response.text)
    (cache / "verify.jsonp").write_text(verify_response.text, encoding="utf-8")
    save_json(cache / "verify.json", verify_json)
    result = verify_json.get("data", {}).get("result")
    summary = {
        "runtime": "pure-python-word",
        "cache": str(cache.resolve()),
        "lot_number": data["lot_number"],
        "ques": [item["text"] for item in ques_items],
        "match": match_info,
        "userresponse": userresponse,
        "passtime": passtime,
        "biht": biht,
        "fixed_fields": fixed_fields,
        "w_length": len(w),
        "status": verify_json.get("status"),
        "result": result,
        "fail_count": verify_json.get("data", {}).get("fail_count"),
    }
    save_json(cache / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description="Pure Python Geetest GT4 word-click replay")
    parser.add_argument("--captcha-id", default=CAPTCHA_ID_DEMO)
    parser.add_argument("--bundle", type=Path, default=Path("js_reverse_cache/gcaptcha4.js"))
    parser.add_argument("--cache-root", type=Path, default=Path("js_reverse_cache/runs"))
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--use-env-proxy", action="store_true")
    parser.add_argument(
        "--manual-point",
        action="append",
        default=[],
        help="Manual image-pixel center as x,y; can repeat in click order",
    )
    parser.add_argument(
        "--captcha-user",
        default="",
        help="captcha_v4_user cookie value from browser",
    )
    parser.add_argument(
        "--device-id",
        default="",
        help="Optional device_id in wPayload; omit by default",
    )
    args = parser.parse_args()

    if not args.bundle.exists():
        raise SystemExit(f"Bundle not found: {args.bundle}")
    fixed_fields, lot_rules = extract_bundle_metadata(args.bundle)
    session = build_session(args.use_env_proxy, captcha_user=args.captcha_user or None)
    args.cache_root.mkdir(parents=True, exist_ok=True)

    ok = 0
    for _ in range(args.rounds):
        summary = solve_once(
            session=session,
            captcha_id=args.captcha_id,
            fixed_fields=fixed_fields,
            lot_rules=lot_rules,
            cache_root=args.cache_root,
            manual_points=args.manual_point or None,
            device_id=args.device_id or None,
        )
        if summary.get("status") == "success" and summary.get("result") == "success":
            ok += 1
    print(json.dumps({"passed": ok, "rounds": args.rounds}, ensure_ascii=False))
    return 0 if ok == args.rounds else 1


if __name__ == "__main__":
    raise SystemExit(main())
