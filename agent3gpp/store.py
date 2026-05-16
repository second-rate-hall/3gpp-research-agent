from __future__ import annotations

import csv
import hashlib
import html.parser
import json
import re
import shutil
import sqlite3
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

from .docx_track_changes import docx_to_markdown


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
INCOMING = DATA / "incoming"
PROCESSED = DATA / "processed"
INDEX = DATA / "index"
METADATA = INDEX / "metadata.csv"
DB = INDEX / "research.db"
USER_AGENT = "3gpp-research-agent/0.1"


@dataclass
class Doc:
    source_id: str
    source_path: str
    processed_path: str
    title: str
    document_type: str
    spec_id: str
    tdoc_id: str
    cr_id: str
    official_url: str
    sha256: str
    parser: str
    parse_status: str


class LinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.links.append(value)


def ensure_dirs() -> None:
    for path in [INCOMING, PROCESSED, INDEX]:
        path.mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:180] or "downloaded"


def request_url(url: str):
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def download(url: str) -> Path:
    ensure_dirs()
    name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name or "index.html"
    target = INCOMING / safe_name(name)
    with urllib.request.urlopen(request_url(url), timeout=90) as response:
        with target.open("wb") as fh:
            shutil.copyfileobj(response, fh)
    target.with_suffix(target.suffix + ".source.json").write_text(
        json.dumps({"url": url}, indent=2), encoding="utf-8"
    )
    return target


def list_url(url: str) -> list[str]:
    with urllib.request.urlopen(request_url(url), timeout=90) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser = LinkParser()
    parser.feed(html)
    return [urllib.parse.urljoin(url.rstrip("/") + "/", link) for link in parser.links]


def spec_archive_url(spec: str) -> str:
    normalized = spec.strip().replace("TS", "").replace("TR", "").replace(" ", "")
    match = re.fullmatch(r"(\d{2})\.?(\d{3})", normalized)
    if not match:
        raise ValueError(f"Bad spec id: {spec}")
    series, rest = match.groups()
    return f"https://www.3gpp.org/ftp/Specs/archive/{series}_series/{series}.{rest}/"


def fetch_spec(spec: str, latest: bool = True, version: str | None = None) -> Path:
    base = spec_archive_url(spec)
    zips = [link for link in list_url(base) if link.lower().endswith(".zip")]
    if not zips:
        raise RuntimeError(f"No archives found for {spec} at {base}")
    if version:
        token = version.lower().replace(".", "")
        candidates = [z for z in zips if token in Path(urllib.parse.urlparse(z).path).stem.lower()]
        if not candidates:
            raise RuntimeError(f"No archive for {spec} matching version {version}")
        chosen = sorted(candidates)[-1]
    else:
        chosen = sorted(zips)[-1] if latest else sorted(zips)[0]
    return download(chosen)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_url(path: Path) -> str:
    sidecar = path.with_suffix(path.suffix + ".source.json")
    if sidecar.exists():
        return json.loads(sidecar.read_text(encoding="utf-8")).get("url", "")
    return ""


def docx_text(path: Path) -> str:
    return docx_to_markdown(path)


def pdf_text(path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return "", "pdf_parser_missing"
    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages), "ok"


def html_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()


def classify(path: Path, text: str = "") -> dict[str, str]:
    name = path.name
    compact = re.search(r"\b(\d{2})(\d{3})[-_.]", name, flags=re.I)
    dotted = re.search(r"\b(\d{2}\.\d{3})\b", name)
    tdoc = re.search(r"\b([RSCGP]\d-\d{6,7})\b", name, flags=re.I)
    cr = re.search(r"\bCR[_ -]?(\d{3,5})\b", name, flags=re.I)
    spec_id = dotted.group(1) if dotted else (f"{compact.group(1)}.{compact.group(2)}" if compact else "")
    doc_type = "spec" if spec_id else ("tdoc" if tdoc else ("cr" if cr else "document"))
    title = next((line.strip().strip("#") for line in text.splitlines() if 8 <= len(line.strip()) <= 160), path.stem)
    return {
        "title": title,
        "document_type": doc_type,
        "spec_id": spec_id,
        "tdoc_id": tdoc.group(1).upper() if tdoc else "",
        "cr_id": cr.group(1) if cr else "",
    }


def write_processed(path: Path, text: str) -> Path:
    target = PROCESSED / f"{path.stem}.{hashlib.sha1(str(path).encode()).hexdigest()[:10]}.md"
    target.write_text(text, encoding="utf-8")
    return target


def parse_file(path: Path, inherited_url: str = "") -> list[Doc]:
    suffix = path.suffix.lower()
    official_url = sidecar_url(path) or inherited_url
    if suffix == ".zip":
        out = PROCESSED / f"{path.stem}.extracted"
        out.mkdir(parents=True, exist_ok=True)
        docs: list[Doc] = []
        with zipfile.ZipFile(path) as zf:
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                target = out / safe_name(member.replace("/", "_"))
                target.write_bytes(zf.read(member))
                docs.extend(parse_file(target, official_url))
        return docs
    status = "ok"
    text = ""
    parser = suffix.lstrip(".") or "unknown"
    if suffix == ".docx":
        text = docx_text(path)
    elif suffix == ".pdf":
        text, status = pdf_text(path)
    elif suffix in {".txt", ".md", ".csv"}:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix in {".html", ".htm"}:
        text = html_text(path)
    else:
        status = "unsupported"
    processed = write_processed(path, text) if text else Path("")
    meta = classify(path, text)
    return [
        Doc(
            source_id=hashlib.sha1(str(path).encode()).hexdigest()[:16],
            source_path=str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
            processed_path=str(processed.relative_to(ROOT)) if processed else "",
            title=meta["title"],
            document_type=meta["document_type"],
            spec_id=meta["spec_id"],
            tdoc_id=meta["tdoc_id"],
            cr_id=meta["cr_id"],
            official_url=official_url,
            sha256=sha256(path),
            parser=parser,
            parse_status=status if text or status != "ok" else "empty",
        )
    ]


def parse_all() -> list[Doc]:
    ensure_dirs()
    docs: list[Doc] = []
    for path in sorted(INCOMING.rglob("*")):
        if path.is_file() and not path.name.endswith(".source.json") and path.name != ".gitkeep":
            docs.extend(parse_file(path))
    write_metadata(docs)
    return docs


def write_metadata(docs: list[Doc]) -> None:
    fields = list(Doc.__dataclass_fields__.keys())
    with METADATA.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for doc in docs:
            writer.writerow(asdict(doc))


def read_metadata() -> list[dict[str, str]]:
    if not METADATA.exists():
        return []
    with METADATA.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def chunks(text: str, size: int = 1800, overlap: int = 250) -> Iterable[tuple[int, str]]:
    i = 0
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        yield i, text[start:end]
        if end == len(text):
            break
        start = max(0, end - overlap)
        i += 1


def build_db() -> None:
    rows = read_metadata()
    con = sqlite3.connect(DB)
    con.executescript(
        """
        DROP TABLE IF EXISTS chunks_fts;
        DROP TABLE IF EXISTS chunks;
        DROP TABLE IF EXISTS documents;
        DROP TABLE IF EXISTS relations;
        CREATE TABLE documents (
          source_id TEXT PRIMARY KEY, source_path TEXT, processed_path TEXT, title TEXT,
          document_type TEXT, spec_id TEXT, tdoc_id TEXT, cr_id TEXT, official_url TEXT,
          sha256 TEXT, parser TEXT, parse_status TEXT
        );
        CREATE TABLE chunks (chunk_id TEXT PRIMARY KEY, source_id TEXT, chunk_index INTEGER, text TEXT);
        CREATE VIRTUAL TABLE chunks_fts USING fts5(text, source_id UNINDEXED, chunk_id UNINDEXED);
        CREATE TABLE relations (
          source_type TEXT, source_id TEXT, relation TEXT, target_type TEXT, target_id TEXT,
          evidence_source TEXT, confidence TEXT, verification_status TEXT
        );
        """
    )
    for row in rows:
        con.execute(
            "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [row.get(k, "") for k in Doc.__dataclass_fields__.keys()],
        )
        processed = ROOT / row.get("processed_path", "")
        if processed.exists():
            text = processed.read_text(encoding="utf-8", errors="replace")
            for idx, chunk in chunks(text):
                chunk_id = f"{row['source_id']}:{idx}"
                con.execute("INSERT INTO chunks VALUES (?,?,?,?)", (chunk_id, row["source_id"], idx, chunk))
                con.execute("INSERT INTO chunks_fts VALUES (?,?,?)", (chunk, row["source_id"], chunk_id))
        if row.get("spec_id"):
            con.execute(
                "INSERT INTO relations VALUES (?,?,?,?,?,?,?,?)",
                (
                    "Document",
                    row["source_id"],
                    "represents",
                    "Specification",
                    row["spec_id"],
                    row.get("official_url") or row.get("source_path"),
                    "high",
                    "confirmed" if row.get("official_url") else "needs_verification",
                ),
            )
    con.commit()
    con.close()


def search(query: str, limit: int = 8, spec_id: str | None = None, match_all: bool = False) -> list[dict[str, str]]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    safe_query = fts_query(query, match_all=match_all)
    where = "WHERE chunks_fts MATCH ?"
    params: list[object] = [safe_query]
    if spec_id:
        where += " AND documents.spec_id = ?"
        params.append(spec_id)
    params.append(limit)
    rows = con.execute(
        """
        SELECT bm25(chunks_fts) AS score, documents.*, chunks.chunk_index, chunks.text,
               snippet(chunks_fts, 0, '[', ']', '...', 24) AS snippet
        FROM chunks_fts
        JOIN chunks ON chunks_fts.chunk_id = chunks.chunk_id
        JOIN documents ON documents.source_id = chunks.source_id
        {where}
        ORDER BY score
        LIMIT ?
        """.format(where=where),
        params,
    ).fetchall()
    if not rows and match_all:
        con.close()
        return search(query, limit=limit, spec_id=spec_id, match_all=False)
    con.close()
    return [dict(row) for row in rows]


def relations(limit: int = 20) -> list[dict[str, str]]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM relations LIMIT ?", (limit,)).fetchall()
    con.close()
    return [dict(row) for row in rows]


def fts_query(text: str, match_all: bool = False) -> str:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}|[\u4e00-\u9fff]{2,}", text)
    if not tokens:
        return f'"{text.replace(chr(34), chr(34) * 2)}"'
    operator = " AND " if match_all else " OR "
    return operator.join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens[:16])
