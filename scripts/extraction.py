"""Fixed approved region extraction; no live image or drawing detection."""

import collections
import hashlib
import json
import math
import re
from pathlib import Path

import pymupdf

LABEL = re.compile(r"(?:\d+|[A-Z]{1,4})-\d+")
EXTRACTOR_VERSION = "aerodoc-approved-regions-v4"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024*1024), b""):
            digest.update(part)
    return digest.hexdigest()


def footer_label(page, footer_height):
    rect = page.rect
    region = pymupdf.Rect(rect.x0, rect.y1-footer_height, rect.x1, rect.y1)
    labels = sorted({s.strip() for s in page.get_text("text", clip=region).splitlines() if LABEL.fullmatch(s.strip())})
    if len(labels)>1:
        raise SystemExit("Multiple footer labels found; inspect the page.")
    return labels[0] if labels else None


def load_figure_regions(config, digest, document, root=None):
    """Fail closed; legacy audit overrides are not extraction inputs anymore."""
    root = root or Path(__file__).resolve().parents[1]
    path = root/config["figure_regions_path"]
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("source_sha256") != digest:
        raise ValueError("Figure region PDF SHA-256 mismatch")
    if value.get("document_id") != config["document_id"]:
        raise ValueError("Figure region document_id mismatch")
    if value.get("schema_version") != 1 or value.get("approval_scope") != "region_boundary_only":
        raise ValueError("Unsupported figure region schema or approval scope")
    by_page, ids, figures = {}, set(), set()
    for r in value["regions"]:
        n, fid, rid = r["pdf_page"], r["figure_id"], r["candidate_id"]
        if type(n) is not int or not 1<=n<=len(document) or not any(a["start"]<=n<=a["end"] for a in config["page_ranges"]):
            raise ValueError("Figure region outside selected PDF pages")
        if rid in ids or (n,fid) in figures:
            raise ValueError("Duplicate active figure region")
        approval = r.get("boundary_approval", {})
        if (r.get("active") is not True or r.get("boundary_review_status") != "human_verified"
                or r.get("approval_scope") != "region_boundary_only"
                or approval.get("accepted") is not True or approval.get("review_status") != "human_verified"
                or approval.get("approval_scope") != "region_boundary_only"
                or any(approval.get(k)!=r[k] for k in ("candidate_id","pdf_page","figure_id","bbox"))):
            raise ValueError("Unapproved region or approval geometry mismatch")
        if r["intended_handling"] not in ("separate_figure","preserve_in_body"):
            raise ValueError("Unsupported figure handling")
        bbox = r["bbox"]
        if not isinstance(bbox,list) or len(bbox)!=4 or not all(type(x) in (int,float) and math.isfinite(x) for x in bbox):
            raise ValueError("Invalid figure bbox")
        x0,y0,x1,y1 = bbox
        rect = document[n-1].rect
        if not (rect.x0<=x0<x1<=rect.x1 and rect.y0<=y0<y1<=rect.y1-config["audit"]["footer_height_points"]):
            raise ValueError("Figure bbox outside page or inside footer")
        if any(pymupdf.Rect(bbox).intersects(pymupdf.Rect(other["bbox"])) for other in by_page.get(n,[])):
            raise ValueError("Overlapping active figure regions")
        ids.add(rid)
        figures.add((n,fid))
        by_page.setdefault(n,[]).append(r)
    for regions in by_page.values():
        regions.sort(key=lambda r:(r["bbox"][1],r["bbox"][0],r["candidate_id"]))
    return {"by_page":by_page,"sha256":sha256(path),"region_version":value["region_version"]}


def extract_page(page, page_number, config, digest, config_hash, region_bundle):
    audit = config["audit"]
    footer_top = page.rect.y1-audit["footer_height_points"]
    split_x = page.rect.x0+page.rect.width*audit["column_split_fraction"]
    warnings = []
    try:
        printed = footer_label(page,audit["footer_height_points"])
    except SystemExit as exc:
        printed = None
        warnings.append(str(exc))
    if printed is None:
        warnings.append("Missing printed page label; inspect the footer.")
    regions = region_bundle["by_page"].get(page_number,[])
    region_blocks = {r["candidate_id"]:[] for r in regions}
    preserved = {r["candidate_id"]:[] for r in regions}
    body, removed, source_ids, ownership = [], [], [], []
    for block in page.get_text("blocks",sort=False):
        if block[6]!=0:
            continue
        x0,y0,x1,y1,raw_text,sid = block[:6]
        source_ids.append(sid)
        item = {"source_block_id":sid,"bbox":[x0,y0,x1,y1],"text":raw_text.strip()}
        if y0>=footer_top:
            removed.append(item)
            ownership.append({"source_block_id":sid,"owner":"footer"})
            continue
        matches = [r for r in regions if pymupdf.Rect(r["bbox"]).contains(pymupdf.Rect(item["bbox"]))]
        if len(matches)>1:
            raise ValueError(f"PDF {page_number}: multiple figure owners for a block")
        if matches:
            r = matches[0]
            if r["intended_handling"]=="separate_figure":
                region_blocks[r["candidate_id"]].append(item)
                ownership.append({"source_block_id":sid,"owner":"figure","region_id":r["candidate_id"]})
                continue
            preserved[r["candidate_id"]].append(sid)
        elif any(pymupdf.Rect(r["bbox"]).intersects(pymupdf.Rect(item["bbox"])) for r in regions):
            warnings.append(f"Source block {sid} partially overlaps a figure region; kept in body for review.")
        if y1>footer_top:
            warnings.append("A body text block intersects the footer region; inspect it.")
        if x0<split_x<x1:
            warnings.append("A text block crosses the column boundary; manual ordering is required.")
        item["column"] = "left" if (x0+x1)/2<split_x else "right"
        body.append(item)
        ownership.append({"source_block_id":sid,"owner":"body"})
    body.sort(key=lambda b:(b["column"]=="right",b["bbox"][1],b["bbox"][0]))
    text = "\n\n".join(b["text"] for b in body if b["text"])+"\n"
    if not text.strip():
        warnings.append("Empty body text; inspect the page.")
    metadata = {"document_id":config["document_id"],"corpus_version":config["corpus_version"],
                "source_sha256":digest,"source_url":config["source_url"],"config_sha256":config_hash,
                "figure_regions_sha256":region_bundle["sha256"],"region_version":region_bundle["region_version"],
                "extractor_version":EXTRACTOR_VERSION,"pymupdf_version":pymupdf.VersionBind,
                "pdf_page":page_number,"printed_page":printed,"chapter":config["chapter"],"human_review_status":"not_reviewed"}
    figures = []
    for r in regions:
        figure = {**metadata,"type":"figure","record_id":f"{config['document_id']}:p{page_number}:{r['figure_id']}",
                  "figure_id":r["figure_id"],"region_id":r["candidate_id"],"bbox":r["bbox"],
                  "intended_handling":r["intended_handling"],"boundary_review_status":"human_verified",
                  "boundary_approval_scope":"region_boundary_only","review_status":"needs_manual_review",
                  "text_order_review_status":"not_reviewed","semantic_relations_review_status":"not_reviewed"}
        if r["intended_handling"]=="preserve_in_body":
            member_ids = set(preserved[r["candidate_id"]])
            figure.update({"content_storage":"page_body_reference","indexable":False,
                           "body_record_id":f"{config['document_id']}:p{page_number}",
                           "source_block_ids":[b["source_block_id"] for b in body if b["source_block_id"] in member_ids],
                           "text_order":"existing_body_order_unverified"})
        else:
            blocks = region_blocks[r["candidate_id"]]
            figure.update({"content_storage":"inline","indexable":True,"blocks":blocks,
                           "text":"\n\n".join(b["text"] for b in blocks if b["text"]),"text_order":"pdf_block_order_unverified"})
            if not blocks:
                warnings.append(f"Configured figure {r['candidate_id']} contains no text blocks; inspect it.")
        figures.append(figure)
    emitted = [b["source_block_id"] for b in body+removed]+[b["source_block_id"] for f in figures for b in f.get("blocks",[])]
    if collections.Counter(emitted)!=collections.Counter(source_ids):
        raise ValueError(f"PDF {page_number}: source block loss or duplication")
    return {**metadata,"type":"page","record_id":f"{config['document_id']}:p{page_number}","indexable":True,
            "extraction_method":"fixed_approved_regions_two_columns_v4","review_status":"needs_manual_review",
            "automatic_status":"warnings" if warnings else "no_warnings","warnings":sorted(set(warnings)),
            "raw_text":page.get_text(),"text":text,"ordered_blocks":body,"removed_footer_blocks":removed,
            "figure_refs":[f["record_id"] for f in figures],"figures":figures,"block_ownership":ownership,
            "source_text_block_count":len(source_ids),"all_source_blocks_preserved_once":True}


def split_records(record):
    """Serialize page references and figure content separately, without text copies."""
    result = dict(record)
    figures = result.pop("figures")
    return result,figures
