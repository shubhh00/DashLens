"""Find, verify and structure the warning-lamp section of a car's owner manual.

Flow: search -> score candidates -> download PDF -> verify it is a real manual
-> keep the lamp pages -> Gemini turns them into JSON -> cache on disk.

Run standalone to test:
    .venv\\Scripts\\python.exe app\\manual_pipeline.py Hyundai Creta
"""
from __future__ import annotations

import difflib
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pypdf import PdfReader

SERVER_DIR = next(p for p in Path(__file__).resolve().parents if (p / "requirements.txt").exists())
load_dotenv(SERVER_DIR / ".env")
load_dotenv(SERVER_DIR / ".env.local", override=True)

CACHE_DIR = SERVER_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-3.8-flash")
# Each model has its own free-tier quota, so a long fallback list stretches the daily budget.
GEMINI_FALLBACK_MODELS = [
    "models/gemini-3.7-flash", "models/gemini-3.6-flash", "models/gemini-3.5-flash",
    "models/gemini-3-flash-preview", "models/gemini-flash-latest",
    "models/gemini-3.5-flash-lite", "models/gemini-3.1-flash-lite", "models/gemini-flash-lite-latest",
]
GEMINI_BUDGET_S = 60  # then fall back to raw lamp pages rather than keep retrying
LAMP_TEXT_LIMIT = 7000
PLACEHOLDER_MODELS = {"unknown", "none", "na", "null", "car", "model", "notsure", "unsure", "any", "generic"}
MIN_LAMPS = 15  # real manuals list 25+; fewer means Gemini returned a partial list (Fronx gave 13)

MIN_SCORE = 7            # below this a URL is not worth downloading
MIN_PAGES = 50           # a real owner's manual is long; a press release is not
MAX_CANDIDATES = 3       # how many PDFs to try before giving up
MAX_PDF_BYTES = 120 * 1024 * 1024  # Maruti's official Fronx manual is 84 MB
USER_AGENT = "Mozilla/5.0 (ClusterAgent manual lookup)"

OEM_DOMAINS = [
    "marutisuzuki.com", "nexaexperience.com", "tatamotors.com",
    "tmlcars.tatamotors.com", "hyundai.com", "mgmotor.co.in",
    "auto.mahindra.com", "kia.com", "toyotabharat.com",
    "hondacarindia.com", "volkswagen.co.in", "skoda-auto.co.in",
]
# Maruti's own sites list every car's manual in these JSON feeds (the pages themselves are JS-only).
MARUTI_FEEDS = {
    "https://www.marutisuzuki.com": "/graphql/execute.json/msil-platform/ArenaCarList",
    "https://www.nexaexperience.com": "/graphql/execute.json/msil-platform/NexaCarList",
}
FOREIGN_HOST = re.compile(r"\.(com?\.)?(au|th|uk|nz|za|my|sg|id|ph|mx|br|jp|de|fr|mm)$")
CDN_HINTS = ["scene7.com", "azurefd.net", "cloudfront.net", "akamaized.net"]
JUNK_DOMAINS = [
    "rocketreach.co", "linkedin.com", "indiamart.com",
    "facebook.com", "youtube.com", "pinterest.com",
]
BAD_WORDS = [
    "brochure", "price", "accessor", "supplementary", "supplement",
    "warranty", "service-manual", "inspection", "checklist", "epaper", "_supp", "cng",
    "booking", "press", "launch",
]
LAMP_KEYWORDS = [
    "warning light", "warning lamp", "indicator light", "telltale",
    "tell-tale", "malfunction indicator", "illuminates", "blinks", "flashes",
]


def log(message: str) -> None:
    print(f"[manual] {message}", flush=True)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


# ---------- 1. find candidate PDFs ----------

def score_candidate(url: str, title: str, make: str, model: str, year: int | None) -> int | None:
    """Return a score, or None to discard. Only orders candidates; verification decides."""
    url_text = unquote(url).lower()
    haystack = slug(url_text + " " + title)
    if slug(model) not in haystack:
        return None  # different car
    both = url_text + " " + title.lower()
    if any(word in both for word in BAD_WORDS):
        return None  # brochure, press release, warranty booklet...
    if "ev" not in slug(model) and (
        slug(model) + "ev" in slug(url_text) or re.search(r"(?<![a-z])(ev|electric)(?![a-z])", url_text)
    ):
        return None  # EV manual for a petrol/diesel car (cretaev.pdf, Nexon-EV-Owner-Manual.pdf)

    score = 0
    if "ownersmanual" in haystack or "ownermanual" in haystack:
        score += 8
    elif "manual" in both or "handbook" in both:
        score += 3
    make_slug = slug(make.split()[0])
    if any(domain in url_text for domain in OEM_DOMAINS):
        score += 5
    elif any(hint in url_text for hint in CDN_HINTS) and make_slug in haystack:
        score += 5  # the OEM's own CDN
    if year and str(year) in url_text:
        score += 3
    # Prefer the current model's manual: "...-jan-2024-to-present.pdf" over "...-sep2020-jan2024.pdf".
    if re.search(r"(?<![a-z])(present|latest|current)(?![a-z])", url_text):
        score += 3
    years = [int(y) for y in re.findall(r"(?<!\d)(20[12]\d)(?!\d)", url_text)]
    if years:
        score += max(0, min(max(years) - 2020, 3))
    # Indian-market manual over the same car sold abroad (Maruti Swift vs Suzuki Swift Australia).
    host = urlparse(url_text).netloc
    if host.endswith(".in") or "/in/" in url_text or "india" in url_text:
        score += 3
    elif FOREIGN_HOST.search(host) or "myanmar" in host:
        score -= 4
    if url_text.split("?")[0].endswith(".pdf"):
        score += 4
    return score


def tavily_search(query: str, include=None, exclude=None) -> list[dict]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        log("TAVILY_API_KEY missing")
        return []
    payload = {"query": query, "search_depth": "basic", "max_results": 10}
    if include:
        payload["include_domains"] = include
    if exclude:
        payload["exclude_domains"] = exclude
    try:
        response = httpx.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        log(f"search failed: {exc}")
        return []
    return response.json().get("results", [])


def pdf_links_on_page(url: str) -> list[str]:
    try:
        response = httpx.get(url, timeout=20.0, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError):
        return []
    hrefs = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', response.text, re.I)
    return [urljoin(url, href) for href in hrefs]


def serper_search(query: str) -> list[dict]:
    """Google results via Serper. Unlike Tavily, Google honours filetype: and site:."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        log("SERPER_API_KEY missing")
        return []
    try:
        response = httpx.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key},
            json={"q": query, "gl": "in", "num": 10},
            timeout=30.0,
        )
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        log(f"serper search failed: {exc}")
        return []
    return [{"url": item.get("link", ""), "title": item.get("title", "")}
            for item in response.json().get("organic", [])]


def maruti_feed_pdfs(make: str, model: str) -> list[dict]:
    """Official Maruti/Nexa manual PDFs for this model, straight from Maruti's own feeds."""
    results = []
    for host, path in MARUTI_FEEDS.items():
        try:
            response = httpx.get(host + path, timeout=30.0, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            log(f"maruti feed failed: {exc}")
            continue
        for pdf_path in sorted(set(re.findall(r'"(/content/dam/[^"]+\.pdf)"', response.text))):
            if slug(model) not in slug(pdf_path):
                continue
            # 99011... is Suzuki's part-number prefix for owner's manuals
            title = f"{make} {model} owner's manual" if "99011" in pdf_path else ""
            results.append({"url": host + pdf_path, "title": title})
    return results


def find_candidates(make: str, model: str, year: int | None, engine: str = "tavily") -> list[str]:
    query = f"{make} {model} owner's manual pdf"
    results = []
    if engine == "oem":
        if slug(make.split()[0]) in ("maruti", "suzuki", "nexa"):
            results += maruti_feed_pdfs(make, model)
    elif engine == "serper":
        results += serper_search(f"{make} {model} owner's manual filetype:pdf")
        results += serper_search(f"{make} {model} owner's manual")
    else:
        results += tavily_search(query, include=OEM_DOMAINS)
        results += tavily_search(query, exclude=JUNK_DOMAINS)
        results += tavily_search(f"{query} filetype:pdf", exclude=JUNK_DOMAINS)

    seen: dict[str, str] = {}
    for result in results:
        url = result.get("url", "")
        if url and url not in seen:
            seen[url] = result.get("title", "")

    pdfs, pages = [], []
    for url, title in seen.items():
        points = score_candidate(url, title, make, model, year)
        if points is None:
            continue
        if url.split("?")[0].lower().endswith(".pdf"):
            pdfs.append((points, url))
        else:
            pages.append((points, url))

    if not pdfs:  # landing-page hop, e.g. OEM "download manuals" pages
        for _, page_url in sorted(pages, reverse=True)[:3]:
            log(f"hopping into {page_url}")
            for pdf_url in pdf_links_on_page(page_url):
                points = score_candidate(pdf_url, "", make, model, year)
                if points is not None:
                    pdfs.append((points, pdf_url))

    pdfs.sort(reverse=True)
    ranked = [url for points, url in pdfs if points >= MIN_SCORE]
    for points, url in pdfs:
        log(f"candidate {points:>3}  {url}")
    return ranked


# ---------- 2. download and verify ----------

def download_pdf(url: str) -> bytes | None:
    try:
        with httpx.stream("GET", url, timeout=60.0, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT}) as response:
            response.raise_for_status()
            chunks, total = [], 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_PDF_BYTES:
                    log("PDF too large, skipping")
                    return None
                chunks.append(chunk)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        log(f"download failed: {exc}")
        return None
    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        log("not actually a PDF")
        return None
    return data


def extract_lamp_text(data: bytes) -> str | None:
    """Return the lamp pages as text, or None if this is not a real manual."""
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        log(f"could not open PDF: {exc}")
        return None
    page_count = len(reader.pages)
    if page_count < MIN_PAGES:
        log(f"only {page_count} pages - not a manual")
        return None

    lamp_pages, roadside_pages = [], []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        lower = text.lower()
        hits = sum(lower.count(keyword) for keyword in LAMP_KEYWORDS)
        if hits:
            lamp_pages.append((hits, index, text))
        if "roadside" in lower and len(roadside_pages) < 2:
            roadside_pages.append((0, index, text))

    top = sorted(lamp_pages, reverse=True)[:25]
    if sum(hits for hits, _, _ in top) < 10:
        log("no real lamp section found - not a manual")
        return None

    keep = sorted(top + roadside_pages, key=lambda item: item[1])
    log(f"verified: {page_count} pages, keeping {len(keep)}")
    joined = "\n\n".join(f"[page {index + 1}]\n{text}" for _, index, text in keep)
    return joined[:120_000]


# ---------- 3. structure with Gemini ----------

def top_lamp_text(text: str, limit: int = LAMP_TEXT_LIMIT) -> str:
    """The most lamp-dense pages, whitespace-collapsed, within `limit` characters."""
    pages = re.split(r"\n\n(?=\[page \d+\])", text)
    ranked = sorted(pages, key=lambda page: -sum(page.lower().count(k) for k in LAMP_KEYWORDS))
    out, used = [], 0
    for page in ranked:
        page = re.sub(r"[ \t]+", " ", re.sub(r"\n{2,}", "\n", page)).strip()
        if used + len(page) > limit:
            page = page[: max(0, limit - used)]
        if page:
            out.append(page)
            used += len(page)
        if used >= limit:
            break
    return "\n\n".join(out)


def structure_lamps(text: str, make: str, model: str) -> dict | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log("GEMINI_API_KEY missing")
        return None
    prompt = f"""Below are pages from the {make} {model} owner's manual.
Extract every warning or indicator lamp they describe.
Return JSON only, in this shape:
{{"lamps": [{{"lamp": "short name", "colour": "red|amber|yellow|green|blue|white",
"steady": "meaning and required action when steady",
"flashing": "meaning and action when flashing, or null if not described"}}],
"roadside_number": "24x7 roadside assistance number if printed, else null"}}
Use only what the pages say. Keep each meaning under 25 words, in plain spoken English."""
    client = genai.Client(api_key=api_key)
    data = None
    # Overloaded models (503/429) are common; retry, then fall back to older models.
    deadline = time.monotonic() + GEMINI_BUDGET_S
    for model_name in dict.fromkeys([GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]):
        if time.monotonic() > deadline:
            log(f"Gemini budget of {GEMINI_BUDGET_S}s used up")
            break
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt, text],
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                data = json.loads(response.text)
                break
            except Exception as exc:
                log(f"Gemini {model_name} attempt {attempt + 1} failed: {str(exc)[:120]}")
                if "503" not in str(exc):
                    break  # quota (429) or unknown model (404): retrying the same model won't help
                time.sleep(3)
        if data is not None and len(data.get("lamps") or []) < MIN_LAMPS:
            log(f"Gemini {model_name} returned only {len(data.get('lamps') or [])} lamps, trying next model")
            data = None
        if data is not None:
            log(f"structured with {model_name}")
            break
    if not data:
        return None
    if not data.get("lamps"):
        log("Gemini returned no lamps")
        return None
    return data


# ---------- 4. the tool ----------

def find_cached(make: str, model: str) -> dict | None:
    """Cached result for this car, allowing near-miss spellings from speech recognition ("Aster" -> astor)."""
    make_key, model_key = slug(make.split()[0]), slug(model)
    exact = CACHE_DIR / f"{make_key}_{model_key}.json"
    if exact.exists():
        log(f"cache hit for {make} {model}")
        return json.loads(exact.read_text(encoding="utf-8"))
    same_make = {path.stem.split("_", 1)[1]: path for path in CACHE_DIR.glob(f"{make_key}_*.json")}
    close = difflib.get_close_matches(model_key, list(same_make), n=1, cutoff=0.75)
    if close:
        log(f"cache hit for {make} {model} (close match: {close[0]})")
        return json.loads(same_make[close[0]].read_text(encoding="utf-8"))
    return None


def lookup_manual(make: str, model: str, year: int | None = None, search: bool = True) -> dict:
    """search=False returns immediately on a cache miss with "fetching": True, for the live voice tool."""
    car = f"{make} {model}".strip()
    if (
        not re.search(r"[a-z]", model.lower())
        or not re.search(r"[a-z]", make.lower())
        or slug(model) in PLACEHOLDER_MODELS  # the LLM sometimes passes "unknown" instead of asking
    ):
        # Empty or year-only model ("", "2024") would match every manual from that brand.
        log(f"rejected lookup: make={make!r} model={model!r}")
        return {
            "source": "none",
            "car": car,
            "note": "The car's make or model name is missing (a year is not a model). "
                    "Ask the driver which model it is, for example Creta, Swift or Nexon, then call lookupManual again.",
        }
    # First word only, so "Maruti Suzuki" / "Tata Motors" / "MG Motor" hit the same file as "Maruti" / "Tata" / "MG".
    cache_file = CACHE_DIR / f"{slug(make.split()[0])}_{slug(model)}.json"
    cached = find_cached(make, model)
    # A text-only entry (Gemini was unavailable) is good enough to answer from now, but full
    # lookups (background/prewarm) retry so it gets upgraded to structured lamps.
    if cached and (cached.get("structured", True) or not search):
        return cached
    if not search:
        return {
            "source": "none",
            "car": car,
            "fetching": True,
            "note": "This car's owner's manual is not loaded yet; it is being fetched now and should be ready "
                    "in a couple of minutes. The model name may have been misheard, so first confirm it with the "
                    "driver. Meanwhile give brief general guidance and say it is general, not from the manual.",
        }

    log(f"looking up {car}")
    tried: set[str] = set()
    for engine in ("oem", "tavily", "serper"):  # each runs only if the previous one's candidates all fail
        log(f"searching with {engine}")
        candidates = [url for url in find_candidates(make, model, year, engine) if url not in tried]
        for url in candidates[:MAX_CANDIDATES]:
            tried.add(url)
            log(f"trying {url}")
            data = download_pdf(url)
            if not data:
                continue
            text = extract_lamp_text(data)
            if not text:
                continue
            structured = structure_lamps(text, make, model)
            if structured:
                result = {
                    "source": "manual",
                    "car": car,
                    "manual_url": url,
                    "roadside_number": structured.get("roadside_number"),
                    "lamps": structured["lamps"],
                }
                log(f"done: {len(result['lamps'])} lamps cached")
            else:
                # Gemini is only a tidy-up step. The PDF is already verified, so hand the voice LLM
                # the manual's own lamp pages instead of giving up (free-tier quota runs out often).
                result = {
                    "source": "manual",
                    "car": car,
                    "manual_url": url,
                    "structured": False,
                    "lamp_text": top_lamp_text(text),
                }
                log(f"done: Gemini unavailable, cached {len(result['lamp_text'])} chars of lamp pages")
            cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result

    log(f"no verified manual for {car}")
    return {
        "source": "none",
        "car": car,
        "note": "No owner's manual could be found and verified for this car. "
                "Tell the driver you are giving general guidance, not manual-specific advice.",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: python app/manual_pipeline.py <make> <model> [year]")
    year_arg = int(sys.argv[3]) if len(sys.argv) > 3 else None
    print(json.dumps(lookup_manual(sys.argv[1], sys.argv[2], year_arg), indent=2))
