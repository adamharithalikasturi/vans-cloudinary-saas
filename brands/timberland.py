# brands/timberland.py
#
# Verified URL pattern (US asset server):
#   https://assets.timberland.com/<ROOT>-<ANGLE>
# ROOT = first 11 characters of the 12-character vendor article number
#   TB12731R0011 -> TB12731R001   (last digit = width digit, dropped)
# ANGLE = HERO, ALT2, ALT3, ALT4, ALTA ...

import re

DEFAULT_BASE = "https://assets.timberland.com/"

# The web form pre-fills the Vans base URL / preset, so Timberland ignores them.
# Set to True only if you want the form values to override.
USE_FRONTEND_VALUES = False

# Images ALT40 and above are not served by the US asset server. They live on the
# Cloudinary delivery host below (same <ROOT>-ALT<n> naming, .jpg extension).
# Other markets' image servers (Taiwan, Japan, Korea...). Used automatically for
# products with NO imagery on the main servers. Add one entry per market once its
# image URL pattern is confirmed, for example:
#   {"key": "TW", "name": "Taiwan",
#    "template": "https://<host>/<path>/{root}{suffix}.jpg",
#    "suffixes": ["-HERO", "-ALT1", "-ALT2", "-ALT3", "-ALT4"]}
# {root} = 11-char image root, {suffix} = one of the suffixes. The first suffix is
# checked first; the rest are only checked if it exists.
REGIONAL_SOURCES = []

HIGH_ALT_BASE = "https://image.timberland.com/image/upload/"
HIGH_ALT_START = 40
HIGH_ALT_END = 55
HIGH_ALT_EXT = ".jpg"

# Confirmed: HERO, ALT2, ALT3, ALT4, ALTA. The rest are guesses.
# After a big run, delete any angle that never returns an image.
SUFFIXES = (
    ["-HERO"]
    + [f"-ALT{i}" for i in range(1, 11)]   # ALT1 .. ALT10
    + [f"-ALT{c}" for c in "ABCDEFGH"]     # ALTA .. ALTH
)

HIGH_SUFFIXES = [f"-ALT{i}" for i in range(HIGH_ALT_START, HIGH_ALT_END + 1)]
SUFFIXES = SUFFIXES + HIGH_SUFFIXES

ALL_UNIQUE_SUFFIXES = list(dict.fromkeys(SUFFIXES))

# main.py checks one "probe" angle per group first and only checks the rest of
# that group for products where the probe exists. Cuts requests by 70-90%.
PROBE_GROUPS = [
    ("-HERO", [s for s in SUFFIXES if s not in HIGH_SUFFIXES and s != "-HERO"]),
    (f"-ALT{HIGH_ALT_START}", [s for s in HIGH_SUFFIXES if s != f"-ALT{HIGH_ALT_START}"]),
]


def _url(base, prefix, root, suffix):
    if suffix in HIGH_SUFFIXES:
        return f"{HIGH_ALT_BASE}{root}{suffix}{HIGH_ALT_EXT}"
    return f"{base}{prefix}{root}{suffix}"

# Clean vendor number: TB + 10 letters/digits (12 characters)
CODE_RE = re.compile(r"^TB[0-9A-Z]{10}$")
ROOT_RE = re.compile(r"^TB[0-9A-Z]{9}$")      # 11 chars: already the image root


def clean_vendor_code(raw):
    """Return a clean 12-char code like TB0A2DHJ0151, or None if not a real product."""
    code = str(raw).strip().upper().replace(" ", "").split("-")[0]   # drop size suffix (TB0A2A8H662-680)
    if code in ("", "NAN", "#", "NOTASSIGNED", "NONE"):
        return None

    # Gifts / packaging rows (GWP_..., TIM_...)
    if code.startswith(("GWP", "TIM")):
        return None

    # SAP variants end with a trailing Z (0A17QX0651Z, TB0250772141Z)
    if code.endswith("Z") and len(code) in (11, 13):
        code = code[:-1]

    # Missing "TB" prefix (0A17QX0651 -> TB0A17QX0651)
    if len(code) == 10 and code[0] == "0":
        code = "TB" + code

    if ROOT_RE.match(code):
        return code          # root supplied directly; treated as its own item code
    return code if CODE_RE.match(code) else None


def _division(row):
    for col in ("MH3 DIVISION", "DIVISION"):
        val = str(row.get(col, "")).upper().strip()
        if val not in ("", "#", "NAN"):
            return val
    return "Not specified"


def scrape_timberland_catalog(df, base_cdn_url, preset):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    if USE_FRONTEND_VALUES:
        base = (base_cdn_url or "").strip() or DEFAULT_BASE
        prefix = f"{preset.strip()}/" if preset and preset.strip() else ""
    else:
        base, prefix = DEFAULT_BASE, ""
    if not base.endswith("/"):
        base += "/"

    item_url_map = {}
    all_urls = set()

    for _, row in df.drop_duplicates(subset=["VENDOR ARTICLE NO."]).iterrows():
        code = clean_vendor_code(row["VENDOR ARTICLE NO."])
        if not code or code in item_url_map:
            continue

        root = code if ROOT_RE.match(code) else code[:-1]
        urls = {s: _url(base, prefix, root, s) for s in SUFFIXES}
        item_url_map[code] = {"root": root, "division": _division(row), "urls": urls}
        all_urls.update(urls.values())

    return item_url_map, all_urls, ALL_UNIQUE_SUFFIXES
