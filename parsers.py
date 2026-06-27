"""Per-document-type parsers + shared helpers for Stage 1 chunking.

Each parser takes (doc_id, doc_meta) and returns a list of schema-complete chunk dicts.
Parsers read document-level metadata from DOCUMENT_REGISTRY (via doc_meta); they never
infer it from the text. All chunk text comes from python-docx via extract.py.
"""

import os
import re

from document_registry import BUNDLE_DIR
from extract import extract_text, iter_blocks

# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

_MONTHS_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTHS_FULL = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}
# Accept abbreviated month names too (the defect log uses "Dec", "Jan", ...).
_MONTHS_FULL.update({name[:3]: num for name, num in list(_MONTHS_FULL.items())})
_TITLES = {"dr", "mr", "mrs", "ms", "miss", "prof", "professor", "sir"}
_SUFFIXES = {"fca", "fcca", "fcma", "kc", "qc", "ca", "cpa", "phd", "obe"}

# All non-universal schema fields, so every chunk is schema-complete (absent -> None).
_OPTIONAL_FIELDS = [
    # contract / amendment
    "clause_number", "clause_heading",
    # witness statement
    "witness_name", "witness_role", "witness_type", "paragraph_number",
    "section_heading",
    # expert report
    "expert_name", "expert_field", "instructed_by", "section_name",
    "is_opinion_section",
    # email
    "sender_name", "sender_org", "recipient_name", "email_datetime",
    "email_subject", "is_internal", "email_position",
    # defect log
    "defect_id", "severity", "cause_attribution", "resolution_date",
]

_DOMAIN_ORG = {
    "meridianretail.co.uk": "Meridian Retail Group",
    "techflow-solutions.co.uk": "TechFlow Solutions",
}


def count_tokens(text):
    """Approximate token count (one consistent heuristic everywhere)."""
    return round(len(text) / 4)


def shorten_title(title):
    """Map a registry title to its formal short form for citations."""
    return {
        "Master Services Agreement": "MSA",
        "Statement of Work (SOW-01)": "SOW",
        "Order Form (Phase 1)": "Order Form",
    }.get(title, title)


def surname_of(name):
    """Last name, dropping leading titles (Dr) and trailing suffixes (FCA)."""
    tokens = [t for t in name.replace(",", " ").split() if t]
    while tokens and tokens[0].lower().rstrip(".") in _TITLES:
        tokens = tokens[1:]
    while tokens and tokens[-1].lower().rstrip(".") in _SUFFIXES:
        tokens = tokens[:-1]
    return tokens[-1] if tokens else name


def format_date_human(value):
    """ISO date or datetime -> '24 Oct 2024'."""
    if not value:
        return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        y, mo, d = m.groups()
        return f"{int(d)} {_MONTHS_ABBR[int(mo) - 1]} {y}"
    return value


def _parse_sent(value):
    """'24 October 2024 16:52' -> '2024-10-24 16:52' (time optional)."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})(?:\s+(\d{1,2}):(\d{2}))?", value)
    if not m:
        return None
    d, mon, y, hh, mm = m.groups()
    mo = _MONTHS_FULL.get(mon.lower())
    if not mo:
        return None
    if hh is not None:
        return f"{y}-{mo:02d}-{int(d):02d} {int(hh):02d}:{mm}"
    return f"{y}-{mo:02d}-{int(d):02d}"


def split_if_long(text, limit=400):
    """Split text at sentence boundaries (full stop + capital) if over `limit` tokens."""
    if count_tokens(text) <= limit:
        return [text]
    sentences = re.split(r"(?<=[.])\s+(?=[A-Z])", text)
    parts, cur = [], ""
    for s in sentences:
        candidate = (cur + " " + s).strip() if cur else s
        if cur and count_tokens(candidate) > limit:
            parts.append(cur.strip())
            cur = s
        else:
            cur = candidate
    if cur.strip():
        parts.append(cur.strip())
    return parts or [text]


def generate_citation(chunk_meta, doc_meta):
    """Auto-generate a formal citation string from metadata (never from chunk text)."""
    doc_type = doc_meta["doc_type"]

    if doc_type in ("contract", "amendment"):
        if chunk_meta.get("clause_number"):
            title_short = shorten_title(doc_meta["doc_title"])
            return f"{title_short}, clause {chunk_meta['clause_number']}"
        return doc_meta["doc_title"]

    elif doc_type == "witness_statement":
        surname = surname_of(doc_meta["witness_name"])
        return f"{surname} WS, para {chunk_meta['paragraph_number']}"

    elif doc_type == "expert_report":
        surname = surname_of(doc_meta["expert_name"])
        return f"{surname} Expert Report, para {chunk_meta['paragraph_number']}"

    elif doc_type in ("email", "internal_email"):
        sender = (chunk_meta.get("sender_name") or "Unknown").split()[-1]
        date_str = format_date_human(chunk_meta.get("email_datetime", ""))
        if doc_meta.get("is_internal"):
            return f"{sender} (internal), {date_str}"
        recipient_full = chunk_meta.get("recipient_name") or ""
        recipient = recipient_full.split()[-1] if recipient_full else ""
        return f"{sender} to {recipient}, {date_str}"

    elif doc_type == "defect_log":
        return f"Defect Log, entry {chunk_meta['defect_id']}"

    elif doc_type == "record":
        date_str = format_date_human(doc_meta["date"])
        return f"{doc_meta['doc_title']}, {date_str}"

    elif doc_type == "letter":
        date_str = format_date_human(doc_meta["date"])
        return f"{doc_meta['author']}, {date_str}"

    return doc_meta["doc_title"]


def make_chunk(doc_id, doc_meta, chunk_id, chunk_text, **extra):
    """Build a schema-complete chunk dict; absent optional fields default to None."""
    chunk = {field: None for field in _OPTIONAL_FIELDS}
    chunk.update({
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "doc_title": doc_meta["doc_title"],
        "doc_type": doc_meta["doc_type"],
        "doc_date": doc_meta["date"],
        "author_party": doc_meta["author_party"],
        "source_quality_weight": doc_meta["source_quality_weight"],
        "is_evidence": doc_meta["is_evidence"],
        "is_legal_argument": doc_meta.get("is_legal_argument", False),
        "chunk_text": chunk_text,
        "token_count": count_tokens(chunk_text),
    })
    # Carry document-level witness/expert metadata from the registry onto every chunk.
    for field in ("witness_name", "witness_role", "witness_type",
                  "expert_name", "expert_field", "instructed_by"):
        if field in doc_meta:
            chunk[field] = doc_meta[field]
    if "is_internal" in doc_meta:
        chunk["is_internal"] = doc_meta["is_internal"]
    # Parser-specific fields override.
    for key, value in extra.items():
        chunk[key] = value
    # Citation generated last, after all metadata is populated.
    chunk["citation"] = generate_citation(chunk, doc_meta)
    return chunk


def _path(doc_meta):
    return os.path.join(BUNDLE_DIR, doc_meta["filename"])


# --------------------------------------------------------------------------- #
# contract / amendment parser  (TAB03, TAB04, TAB05, TAB06, TAB07)
# --------------------------------------------------------------------------- #

def _clause_token(line):
    """Return the leading clause-number token (N. / N.N / N.N.N) or None."""
    if not line or not line[0].isdigit():
        return None
    sp = line.find(" ")
    token = line if sp == -1 else line[:sp]
    if re.fullmatch(r"\d+\.", token) or re.fullmatch(r"\d+\.\d+", token) \
            or re.fullmatch(r"\d+\.\d+\.\d+", token):
        return token
    return None


def _emit_clause(chunks, doc_id, doc_meta, num, heading, body):
    body = body.strip()
    if not body:
        return
    key = num.replace(".", "_")
    parts = split_if_long(body, 400)
    if len(parts) == 1:
        cid = f"{doc_id}_clause_{key}_0"
        chunks.append(make_chunk(doc_id, doc_meta, cid, body,
                                 clause_number=num, clause_heading=heading))
    else:
        for i, part in enumerate(parts, 1):
            cid = f"{doc_id}_clause_{key}_part_{i}"
            chunks.append(make_chunk(doc_id, doc_meta, cid, part,
                                     clause_number=num, clause_heading=heading))


def parse_contract(doc_id, doc_meta):
    # The Order Form (TAB05) carries its substance in a table, not in clauses.
    if doc_id == "TAB05":
        return parse_order_form(doc_id, doc_meta)

    lines = extract_text(_path(doc_meta)).split("\n")
    chunks = []
    current_heading = None
    cur = None  # {"num": str, "lines": [str]}

    def flush():
        nonlocal cur
        if cur is not None and cur["lines"]:
            _emit_clause(chunks, doc_id, doc_meta, cur["num"], current_heading,
                         " ".join(cur["lines"]))
        cur = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        token = _clause_token(line)
        if token is None:
            if cur is not None:           # continuation of an open clause
                cur["lines"].append(line)
            continue
        rest = line[len(token):].strip()
        if re.fullmatch(r"\d+\.", token):
            # Top-level: a short heading phrase, or (rarely) a standalone clause.
            words = rest.split()
            if rest and len(words) <= 8 and not rest.endswith("."):
                flush()
                current_heading = rest
            else:
                flush()
                cur = {"num": token.rstrip("."), "lines": [rest] if rest else []}
        else:
            # Subclause N.N (or N.N.N): a new chunk boundary.
            flush()
            cur = {"num": token, "lines": [rest] if rest else []}
    flush()
    return chunks


def parse_order_form(doc_id, doc_meta):
    chunks = []
    n = 0
    for kind, content in iter_blocks(_path(doc_meta)):
        if kind != "table":
            continue
        for row in content:
            cells = [c.strip() for c in row]
            if len(cells) < 3 or not cells[0]:
                continue
            item, qty, charge = cells[0], cells[1], cells[2]
            low = item.lower()
            if low == "item" or low.startswith("total"):
                continue
            n += 1
            text = f"{item} — Qty: {qty or 'n/a'} — Charge (£): {charge}"
            chunks.append(make_chunk(doc_id, doc_meta, f"{doc_id}_item_{n}", text))
    return chunks


# --------------------------------------------------------------------------- #
# witness_statement parser  (TAB16, TAB17, TAB18)
# --------------------------------------------------------------------------- #

def _is_section_heading(s):
    if not s or s.endswith("."):
        return False
    return len(s.split()) <= 9


def parse_witness(doc_id, doc_meta):
    lines = extract_text(_path(doc_meta)).split("\n")
    chunks = []
    section = None
    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(\d+)\.\s*(.+)$", line)
        if m and count_tokens(m.group(2)) >= 10:
            num = int(m.group(1))
            text = m.group(2).strip()
            parts = split_if_long(text, 400)
            for i, part in enumerate(parts, 1):
                suffix = "" if len(parts) == 1 else f"_part_{i}"
                cid = f"{doc_id}_para_{num}{suffix}"
                chunks.append(make_chunk(doc_id, doc_meta, cid, part,
                                         paragraph_number=num,
                                         section_heading=section))
        elif _is_section_heading(s):
            section = s
    return chunks


# --------------------------------------------------------------------------- #
# expert_report parser  (TAB19, TAB20)
# --------------------------------------------------------------------------- #

def parse_expert(doc_id, doc_meta):
    lines = extract_text(_path(doc_meta)).split("\n")
    chunks = []
    section_name = None
    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^(\d+)\.(.*)$", line)
        if not m:
            continue
        num = int(m.group(1))
        rest = m.group(2)
        rest_stripped = rest.strip()
        # Section heading: number, dot, 2+ spaces, short title, no terminal punctuation.
        if re.match(r"^ {2,}\S", rest) and len(rest_stripped.split()) <= 8 \
                and not rest_stripped.endswith((".", ",", ";")):
            section_name = rest_stripped
            continue
        # Otherwise a numbered paragraph.
        if count_tokens(rest_stripped) < 5:
            continue
        is_opinion = bool(section_name and "opinion" in section_name.lower())
        parts = split_if_long(rest_stripped, 400)
        for i, part in enumerate(parts, 1):
            suffix = "" if len(parts) == 1 else f"_part_{i}"
            cid = f"{doc_id}_para_{num}{suffix}"
            chunks.append(make_chunk(doc_id, doc_meta, cid, part,
                                     paragraph_number=num,
                                     section_name=section_name,
                                     is_opinion_section=is_opinion))
    return chunks


# --------------------------------------------------------------------------- #
# email_thread / internal_email parser  (TAB09-11, TAB12)
# --------------------------------------------------------------------------- #

_HEADER_KEYS = {"from", "to", "cc", "sent", "subject"}


def _sender_org(from_value):
    m = re.search(r"@([\w.-]+)", from_value)
    if not m:
        return None
    domain = m.group(1).lower()
    if domain in _DOMAIN_ORG:
        return _DOMAIN_ORG[domain]
    return domain.split(".")[0].replace("-", " ").title()


def _name_before_angle(value):
    return value.split("<")[0].strip() or None


def parse_email(doc_id, doc_meta):
    single = doc_meta["doc_type"] == "internal_email"
    emails = []
    cur = None
    for kind, content in iter_blocks(_path(doc_meta)):
        if kind == "table":
            for row in content:
                if not row or not row[0]:
                    continue
                key = row[0].strip().rstrip(":").strip().lower()
                value = row[1].strip() if len(row) > 1 else ""
                if key not in _HEADER_KEYS:
                    continue
                if key == "from":
                    cur = {"headers": {}, "body": []}
                    emails.append(cur)
                if cur is not None:
                    cur["headers"][key] = value
        else:  # paragraph
            text = content.strip()
            if text and cur is not None:
                cur["body"].append(text)

    # Build chunk metadata per email.
    built = []
    for e in emails:
        h = e["headers"]
        built.append({
            "sender_name": _name_before_angle(h.get("from", "")),
            "sender_org": _sender_org(h.get("from", "")),
            "recipient_name": _name_before_angle(h.get("to", "")),
            "email_datetime": _parse_sent(h.get("sent", "")),
            "email_subject": h.get("subject") or None,
            "body": "\n".join(e["body"]).strip(),
        })

    # email_position by chronological Sent order (1 = earliest).
    order = sorted(range(len(built)),
                   key=lambda i: built[i]["email_datetime"] or "")
    position = {idx: rank + 1 for rank, idx in enumerate(order)}

    chunks = []
    for i, e in enumerate(built):
        if single:
            cid = f"{doc_id}_email_0"
        else:
            cid = f"{doc_id}_email_{position[i]}"
        chunks.append(make_chunk(
            doc_id, doc_meta, cid, e["body"],
            sender_name=e["sender_name"], sender_org=e["sender_org"],
            recipient_name=e["recipient_name"], email_datetime=e["email_datetime"],
            email_subject=e["email_subject"],
            email_position=None if single else position[i],
        ))
        if single:
            break
    return chunks


# --------------------------------------------------------------------------- #
# defect_log parser  (TAB13)
# --------------------------------------------------------------------------- #

def _normalise_cause(status_cause):
    low = status_cause.lower()
    if "store network" in low:
        return "Store network"
    if "network" in low:
        return "Network (Northgate Telecom)"
    if "platform" in low:
        return "Platform"
    return None


def _resolution_date(status_cause):
    m = re.search(r"fixed\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", status_cause)
    if not m:
        return None
    d, mon, y = m.groups()
    mo = _MONTHS_FULL.get(mon.lower())
    if not mo:
        return None
    return f"{y}-{mo:02d}-{int(d):02d}"


def parse_defect_log(doc_id, doc_meta):
    chunks = []
    for kind, content in iter_blocks(_path(doc_meta)):
        if kind != "table":
            continue
        for row in content:
            cells = [c.strip() for c in row]
            if len(cells) < 5 or not re.match(r"^D-\d+", cells[0]):
                continue
            defect_id, date_raised, severity, description, status_cause = cells[:5]
            text = (f"{defect_id} ({date_raised}, {severity}): {description}. "
                    f"Status: {status_cause}")
            cid = f"{doc_id}_{defect_id.replace('-', '_')}"
            chunks.append(make_chunk(
                doc_id, doc_meta, cid, text,
                defect_id=defect_id, severity=severity,
                cause_attribution=_normalise_cause(status_cause),
                resolution_date=_resolution_date(status_cause),
            ))
    return chunks


# --------------------------------------------------------------------------- #
# letter parser  (TAB14, TAB15)
# --------------------------------------------------------------------------- #

def parse_letter(doc_id, doc_meta):
    lines = [l.strip() for l in extract_text(_path(doc_meta)).split("\n")]
    chunks = []
    n = 0
    for line in lines:
        if not line:
            continue
        # Substantive prose only; this threshold cleanly drops letterhead,
        # addressee block, date, salutation, subject heading and sign-off.
        if count_tokens(line) < 30:
            continue
        n += 1
        chunks.append(make_chunk(doc_id, doc_meta, f"{doc_id}_para_{n}", line))
    return chunks


# --------------------------------------------------------------------------- #
# record parser  (TAB08 — UAT Acceptance Certificate)
# --------------------------------------------------------------------------- #

def parse_record(doc_id, doc_meta):
    lines = [l.strip() for l in extract_text(_path(doc_meta)).split("\n") if l.strip()]
    body = [l for l in lines if count_tokens(l) >= 30]
    text = " ".join(body).strip()
    return [make_chunk(doc_id, doc_meta, f"{doc_id}_record_0", text)]


# --------------------------------------------------------------------------- #
# pleading parser  (TAB01, TAB02 — not evidence)
# --------------------------------------------------------------------------- #

def parse_pleading(doc_id, doc_meta):
    lines = [l.rstrip() for l in extract_text(_path(doc_meta)).split("\n")]
    chunks = []
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        m = re.match(r"^(\d+)\.\s*(.+)$", raw)
        if m and count_tokens(m.group(2)) >= 15:
            num = int(m.group(1))
            chunks.append(make_chunk(doc_id, doc_meta, f"{doc_id}_para_{num}",
                                     m.group(2).strip(), paragraph_number=num))
    if not chunks:  # fallback: substantive prose paragraphs
        n = 0
        for raw in lines:
            s = raw.strip()
            if s and count_tokens(s) >= 30:
                n += 1
                chunks.append(make_chunk(doc_id, doc_meta, f"{doc_id}_para_{n}", s))
    return chunks


# --------------------------------------------------------------------------- #
# Dispatch table by doc_type
# --------------------------------------------------------------------------- #

PARSERS = {
    "contract": parse_contract,
    "amendment": parse_contract,
    "witness_statement": parse_witness,
    "expert_report": parse_expert,
    "email": parse_email,
    "internal_email": parse_email,
    "defect_log": parse_defect_log,
    "letter": parse_letter,
    "record": parse_record,
    "pleading": parse_pleading,
}
