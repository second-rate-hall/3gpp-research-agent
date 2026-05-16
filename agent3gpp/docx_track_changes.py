from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TEXT_TAGS = {f"{{{W_NS}}}t", f"{{{W_NS}}}delText"}
PARA_TAG = f"{{{W_NS}}}p"
INS_TAG = f"{{{W_NS}}}ins"
DEL_TAG = f"{{{W_NS}}}del"
TAB_TAG = f"{{{W_NS}}}tab"
BR_TAG = f"{{{W_NS}}}br"


@dataclass
class TrackStats:
    inserted_segments: int = 0
    deleted_segments: int = 0
    paragraphs: int = 0


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def merge_segments(segments: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for status, text in segments:
        if not text:
            continue
        if merged and merged[-1][0] == status:
            merged[-1] = (status, merged[-1][1] + text)
        else:
            merged.append((status, text))
    return [(status, clean_text(text)) for status, text in merged if clean_text(text)]


def collect_segments(node: ElementTree.Element, status: str = "normal") -> list[tuple[str, str]]:
    current = status
    if node.tag == INS_TAG:
        current = "inserted"
    elif node.tag == DEL_TAG:
        current = "deleted"

    segments: list[tuple[str, str]] = []
    if node.tag in TEXT_TAGS and node.text:
        text_status = "deleted" if node.tag.endswith("}delText") else current
        segments.append((text_status, node.text))
    elif node.tag == TAB_TAG:
        segments.append((current, "\t"))
    elif node.tag == BR_TAG:
        segments.append((current, "\n"))

    for child in list(node):
        segments.extend(collect_segments(child, current))
        if child.tail:
            segments.append((current, child.tail))
    return merge_segments(segments)


def paragraph_to_markdown(paragraph: ElementTree.Element, stats: TrackStats) -> str:
    stats.paragraphs += 1
    lines: list[str] = []
    for status, text in collect_segments(paragraph):
        if status == "inserted":
            stats.inserted_segments += 1
            lines.append(f"+ {text}")
        elif status == "deleted":
            stats.deleted_segments += 1
            lines.append(f"- {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def docx_to_markdown(path: Path) -> str:
    stats = TrackStats()
    parts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.startswith("word/") and n.endswith(".xml")]
        xml_names = ["word/document.xml"] + [n for n in names if n != "word/document.xml"]
        for name in xml_names:
            if name not in zf.namelist():
                continue
            try:
                root = ElementTree.fromstring(zf.read(name))
            except ElementTree.ParseError:
                continue
            blocks = []
            for paragraph in root.iter(PARA_TAG):
                rendered = paragraph_to_markdown(paragraph, stats)
                if rendered:
                    blocks.append(rendered)
            if blocks:
                parts.append(f"<!-- DOCX part: {name} -->\n\n" + "\n\n".join(blocks))
    header = [
        "<!-- 3GPP DOCX track-changes aware extraction -->",
        f"<!-- inserted_segments={stats.inserted_segments}; deleted_segments={stats.deleted_segments}; paragraphs={stats.paragraphs} -->",
        "<!-- Lines beginning with '+' are Word insertions; '-' are Word deletions. Do not treat deleted text as current standard text. -->",
        "",
    ]
    return "\n".join(header) + "\n\n".join(parts).strip()
