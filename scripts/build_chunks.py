"""Source-traceable minimum normalization and BGE-tokenized chunks; no embeddings."""

import argparse
import collections
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import statistics
from pathlib import Path

import pymupdf

from chunking import HYPHEN, Mapped, ModelTokenizer, combine, normalize, split_group, stable_id, trace_spans

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def sha(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):
            digest.update(part)
    return digest.hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def jsonl(path,items):
    path.write_bytes("".join(json.dumps(x,ensure_ascii=False,separators=(",",":"))+"\n" for x in items).encode("utf-8"))


def registry(pages,figures):
    sources={}
    footer_keys=set()
    for page in pages:
        for b in page["removed_footer_blocks"]:
            footer_keys.add(f"p{page['pdf_page']}:b{b['source_block_id']}")
        for b in page["ordered_blocks"]:
            key=f"p{page['pdf_page']}:b{b['source_block_id']}"
            sources[key]={**b,"block_key":key,"raw_text":b["text"],"owner":"body",
                          "pdf_page":page["pdf_page"],"printed_page":page["printed_page"]}
    for f in figures:
        if f["content_storage"]=="page_body_reference":
            if f["indexable"]:
                raise ValueError("Body-reference figure must not be separately indexable")
            for sid in f["source_block_ids"]:
                if f"p{f['pdf_page']}:b{sid}" not in sources:
                    raise ValueError("Unresolvable body-reference figure")
            continue
        if f["content_storage"]!="inline" or not f["indexable"]:
            raise ValueError("Unsupported figure storage policy")
        for b in f["blocks"]:
            key=f"p{f['pdf_page']}:b{b['source_block_id']}"
            if key in sources:
                raise ValueError("Duplicate body/figure source owner")
            sources[key]={**b,"block_key":key,"raw_text":b["text"],"owner":"figure","figure_id":f["figure_id"],
                          "pdf_page":f["pdf_page"],"printed_page":f["printed_page"]}
    if footer_keys.intersection(sources):
        raise ValueError("Footer source included in eligible text")
    return sources,footer_keys


def hyphen_evidence(pdf,sources,source_hash,cache):
    candidates=sorted({(m[1]+m[2]).lower() for s in sources.values() for m in HYPHEN.finditer(s["raw_text"])})
    value=read(cache) if cache.exists() else None
    if not value or value.get("source_sha256")!=source_hash or value.get("candidates")!=candidates:
        evidence={word:[] for word in candidates}
        for i,page in enumerate(pdf):
            for b in page.get_text("blocks",sort=False):
                if b[6]!=0:
                    continue
                for word in candidates:
                    for match in re.finditer(r"(?<![\w-])"+re.escape(word)+r"(?![\w-])",b[4],re.I):
                        evidence[word].append({"pdf_page":i+1,"source_block_id":b[5],"raw_start":match.start(),
                                               "raw_end":match.end(),"raw_text":b[4]})
            if (i+1)%100==0:
                print(f"Hyphen evidence: scanned PDF page {i+1}",flush=True)
        value={"source_sha256":source_hash,"page_count":len(pdf),"candidates":candidates,"evidence":evidence}
        save(cache,value)
    # Verify every positive proof against the actual PDF; never trust a cached word list alone.
    for word,proofs in value["evidence"].items():
        for proof in proofs:
            raw=next(b[4] for b in pdf[proof["pdf_page"]-1].get_text("blocks",sort=False)
                     if b[6]==0 and b[5]==proof["source_block_id"])
            if raw!=proof["raw_text"] or raw[proof["raw_start"]:proof["raw_end"]].lower()!=word:
                raise ValueError("Invalid source evidence for word join")
            if not re.fullmatch(r"[A-Za-z]+",raw[proof["raw_start"]:proof["raw_end"]]):
                raise ValueError("Hyphen join requires a complete unhyphenated source word")
            if not any(m.start()==proof["raw_start"] and m.end()==proof["raw_end"] for m in
                       re.finditer(r"(?<![\w-])"+re.escape(word)+r"(?![\w-])",raw,re.I)):
                raise ValueError("Hyphen evidence is not a whole source word")
    return value["evidence"]


def heading_ranges(source,pdf_blocks):
    """Use bbox matching: dict block numbers differ from text-block IDs when images exist."""
    raw=source["raw_text"]
    block=next((b for b in pdf_blocks if b.get("type")==0 and
                all(abs(x-y)<.05 for x,y in zip(b["bbox"],source["bbox"]))),None)
    if block is None:
        return [],"no_matching_pdf_style_block"
    styled={}
    for line in block.get("lines",[]):
        spans=[s for s in line["spans"] if s["text"].strip()]
        text="".join(s["text"] for s in line["spans"]).strip()
        if spans and text and len(text)<=85 and len(text.split())<=10 and all(s["flags"]&16 and s["size"]>=9.9 for s in spans):
            styled[" ".join(text.split())]=True
    result=[]
    pos=0
    for line in raw.splitlines(keepends=True):
        title=line.strip()
        if (" ".join(title.split()) in styled or title=="Human Factors" or re.fullmatch(r"Chapter \d+",title)) and not re.match(r"(?:\d+[.)]|[•*])\s",title):
            result.append({"raw_start":pos,"raw_end":pos+len(line),"title":title,"hierarchy":"flat_no_nested_inference"})
        pos+=len(line)
    return result,None


def prepare_blocks(sources,pages,pdf,evidence):
    prepared,logs,headings,uncertainties={},[],[],[]
    pdf_styles={}
    for page in pages:
        if page["pdf_page"]!=655:
            pdf_styles[page["pdf_page"]]=pdf[page["pdf_page"]-1].get_text("dict")["blocks"]
    for key,source in sources.items():
        raw=source["raw_text"]
        found=[]
        if source["owner"]=="body" and source["pdf_page"]!=655:
            found,uncertainty=heading_ranges(source,pdf_styles[source["pdf_page"]])
            if uncertainty:
                uncertainties.append({"block_key":key,"reason":uncertainty})
        spans=[]
        cursor=0
        for heading in found:
            if cursor<heading["raw_start"]:
                spans.append((cursor,heading["raw_start"],None))
            spans.append((heading["raw_start"],heading["raw_end"],heading))
            cursor=heading["raw_end"]
            headings.append({"block_key":key,"pdf_page":source["pdf_page"],**heading})
        if cursor<len(raw):
            spans.append((cursor,len(raw),None))
        units=[]
        for start,end,heading in spans:
            mapped,changes=normalize(raw[start:end],key,start,evidence,preserve_lines=source["owner"]=="figure")
            logs.extend({**change,"pdf_page":source["pdf_page"],"printed_page":source["printed_page"],
                         "source_block_id":source["source_block_id"]} for change in changes)
            if mapped.text:
                units.append({"mapped":mapped,"heading":heading,"block_key":key})
        prepared[key]=units
    return prepared,logs,headings,uncertainties


def build_groups(pages,figures,sources,prepared,logs):
    groups=[]
    current=None
    chapter=None
    latest=None
    def new_group(path,**extra):
        group={"group_id":f"body-section-{len(groups):04}","type":"body","section_path":path,
               "units":[],"figure_id":None,"caption":None,**extra}
        groups.append(group)
        return group
    previous_source=None
    for page in pages:
        if page["pdf_page"]==655:
            ref=next(f for f in figures if f["pdf_page"]==655 and f["content_storage"]=="page_body_reference")
            caption=next(b["text"] for b in page["ordered_blocks"] if b["text"].startswith("Figure "))
            pair=0
            for block in page["ordered_blocks"]:
                key=f"p655:b{block['source_block_id']}"
                if block["text"] in ("INCIDENT","ACCIDENT"):
                    pair+=1
                    current=new_group([chapter] if chapter else [],group_id=f"p655-pair-{pair}",
                                      figure_id=ref["figure_id"],caption=caption,event_cause_pair_id=f"p655-pair-{pair}")
                if current is None or not current.get("event_cause_pair_id"):
                    raise ValueError("Unrecognized preserve-in-body event/cause layout")
                current["units"].extend(prepared[key])
            if pair!=5:
                raise ValueError("Expected five separately preserved event/cause pairs")
            continue
        for block in page["ordered_blocks"]:
            key=f"p{page['pdf_page']}:b{block['source_block_id']}"
            source=sources[key]
            for unit in prepared[key]:
                heading=unit["heading"]
                if heading:
                    title=heading["title"]
                    if title==page["chapter"]:
                        chapter=title
                        latest=None
                    elif not re.fullmatch(r"Chapter \d+",title):
                        latest=title
                    path=([chapter] if chapter else [])+([latest] if latest and latest!=chapter else [])
                    if current is not None and current["units"] and all(u["heading"] for u in current["units"]):
                        # Consecutive source headings belong before the following
                        # text, rather than becoming empty standalone retrieval hits.
                        current["section_path"]=path
                    else:
                        current=new_group(path)
                elif current is None:
                    current=new_group([])
                # A physical page/column continuation can join a paragraph only
                # without an intervening heading, unfinished punctuation and a lowercase start.
                can_join=(not heading and current["units"] and previous_source is not None
                          and current["units"][-1]["heading"] is None
                          and (previous_source["pdf_page"]!=source["pdf_page"] or previous_source.get("column")!=source.get("column"))
                          and not re.search(r"[.!?:;][\"'’)]*$",current["units"][-1]["mapped"].text)
                          and unit["mapped"].text[:1].islower())
                if can_join:
                    previous=current["units"][-1]
                    logs.append({"operation":"physical_boundary_continuation","left_block_key":previous_source["block_key"],
                                 "right_block_key":key,"left_pdf_page":previous_source["pdf_page"],"right_pdf_page":source["pdf_page"]})
                    previous["mapped"]=combine([previous["mapped"],unit["mapped"]]," ")
                else:
                    current["units"].append({**unit})
                previous_source=source
    for f in figures:
        if f["content_storage"]=="page_body_reference":
            continue  # Never turn the same body reference into a second text stream.
        units=[]
        for b in f["blocks"]:
            units.extend(prepared[f"p{f['pdf_page']}:b{b['source_block_id']}"])
        caption=next((b["text"] for b in f["blocks"] if re.match(r"^Figure\s+\d+-\d+\.",b["text"])),None)
        groups.append({"group_id":f["record_id"],"type":"figure","section_path":[],"units":units,
                       "figure_id":f["figure_id"],"caption":caption,"figure_text_order":f["text_order"],
                       "boundary_approval_scope":"region_boundary_only"})
    return [g for g in groups if g["units"]]


def validate_chunks(chunks,internal,sources,footers,logs,tokenizer,config):
    primary=collections.Counter()
    overlap=collections.Counter()
    removed=set()
    for log in logs:
        if log.get("status")=="joined":
            start,end=log["removed_raw_range"]
            if not log.get("support") or not re.fullmatch(r"-\s*",sources[log["block_key"]]["raw_text"][start:end]):
                raise ValueError("Invalid nonwhitespace normalization removal")
            removed.update((log["block_key"],i) for i in range(start,end) if not sources[log["block_key"]]["raw_text"][i].isspace())
    for chunk,detail in zip(chunks,internal):
        if chunk["text"]!=detail["mapped"].text or chunk["source_refs"]!=trace_spans(detail["mapped"],detail["roles"],sources):
            raise ValueError("Serialized source references do not match character provenance")
        if tokenizer.count(chunk["text"])!=chunk["token_count"] or chunk["token_count"]>config["max_tokens"]:
            raise ValueError("Token accounting failed")
        if chunk["overlap_token_count"]>config["max_overlap_tokens"]:
            raise ValueError("Overlap limit exceeded")
        overlap_text="".join(c for c,role in zip(detail["mapped"].text,detail["roles"]) if role=="overlap")
        if chunk["overlap_token_count"]!=(tokenizer.count(overlap_text,False) if overlap_text else 0):
            raise ValueError("Overlap token accounting failed")
        for char,origin,role in zip(detail["mapped"].text,detail["mapped"].origins,detail["roles"]):
            if origin is None:
                if not char.isspace():
                    raise ValueError("Invented non-source text in model input")
                continue
            key,start,end=origin
            if key in footers or not 0<=start<end<=len(sources[key]["raw_text"]):
                raise ValueError("Invalid source reference/footer leak")
            counter=overlap if role=="overlap" else primary
            for pos in range(start,end):
                if not sources[key]["raw_text"][pos].isspace():
                    counter[(key,pos)]+=1
        refs=chunk["source_refs"]
        if chunk["pdf_pages"]!=sorted({r["pdf_page"] for r in refs}):
            raise ValueError("Chunk pages include unused context")
        if chunk["printed_pages"]!=list(dict.fromkeys(r["printed_page"] for r in refs)) or chunk["source_block_ids"]!=list(dict.fromkeys(r["block_key"] for r in refs)):
            raise ValueError("Chunk metadata contains unused source blocks/pages")
        if chunk["type"]=="figure" and chunk["figure_id"]=="14-37":
            raise ValueError("Duplicate preserve_in_body text stream")
    expected={(key,i) for key,s in sources.items() for i,c in enumerate(s["raw_text"]) if not c.isspace()}-removed
    missing=expected-set(primary)
    extra=set(primary)-expected
    duplicate=[key for key,count in primary.items() if count!=1]
    if missing or extra or duplicate:
        raise ValueError(f"Coverage failure: missing={len(missing)}, extra={len(extra)}, primary duplicates={len(duplicate)}")
    if len({c["chunk_id"] for c in chunks})!=len(chunks):
        raise ValueError("Duplicate chunk IDs")
    return {"eligible_source_blocks":len(sources),"eligible_nonwhitespace_characters":len(expected)+len(removed),
            "primary_covered_characters":len(primary),"proven_join_removed_characters":len(removed),
            "intentional_overlap_character_copies":sum(overlap.values()),"unintended_primary_duplicates":0,
            "missing_characters":0,"footer_references":0,"preserve_in_body_figure_copies":0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=ROOT/"config/chunking.json")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    config=read(args.config)
    if not (0<=config["overlap_tokens"]<=config["max_overlap_tokens"]<=50
            and 0<config["target_tokens"]<=config["max_tokens"]<=500) or config["heading_context"]!="none":
        raise ValueError("Unsupported chunk/token/context policy")
    out=args.output or ROOT/config["output_dir"]
    out.mkdir(parents=True,exist_ok=True)
    pages=lines(ROOT/config["pages_path"])
    figures=lines(ROOT/config["figures_path"])
    corpus=read(ROOT/"config/corpus.json")
    pdf_path=ROOT/corpus["pdf_path"]
    source_hash=sha(pdf_path)
    if any(r["source_sha256"]!=source_hash for r in pages+figures):
        raise ValueError("Extraction and source PDF do not match")
    tokenizer_config=config["tokenizer"]
    cache=ROOT/tokenizer_config["cache_dir"]
    for name,digest in tokenizer_config["files"].items():
        if not (cache/name).exists() or sha(cache/name)!=digest:
            raise ValueError("Run scripts/fetch_chunk_tokenizer.py: missing/changed pinned tokenizer artifact "+name)
    tokenizer=ModelTokenizer(cache/"tokenizer.json")
    if tokenizer.count("test")!=3:
        raise ValueError("Unexpected BGE special-token processing")
    sources,footers=registry(pages,figures)
    input_paths=[ROOT/config["pages_path"],ROOT/config["figures_path"],ROOT/"config/figure_regions.json",ROOT/"eval/dev_questions.json"]
    initial={str(p.relative_to(ROOT)):sha(p) for p in input_paths}
    with pymupdf.open(pdf_path) as pdf:
        evidence=hyphen_evidence(pdf,sources,source_hash,ROOT/config["output_dir"]/"hyphen_evidence.json")
        prepared,logs,headings,uncertainties=prepare_blocks(sources,pages,pdf,evidence)
    groups=build_groups(pages,figures,sources,prepared,logs)
    chunks,internal,forced=[],[],[]
    base={k:pages[0][k] for k in ("document_id","corpus_version","source_sha256")}
    for group in groups:
        mapped=combine([u["mapped"] for u in group["units"]])
        # Each event/cause pair is its own group and has no overlap with another pair.
        parts,splits=split_group(mapped,tokenizer,config["target_tokens"],config["max_tokens"],
                                 0 if group.get("event_cause_pair_id") else config["overlap_tokens"])
        forced.extend({"group_id":group["group_id"],**s} for s in splits)
        for number,part in enumerate(parts,1):
            refs=trace_spans(part["mapped"],part["roles"],sources)
            payload={**base,"type":group["type"],"text":part["mapped"].text,"token_count":part["token_count"],
                     "pdf_pages":sorted({r["pdf_page"] for r in refs}),
                     "printed_pages":list(dict.fromkeys(r["printed_page"] for r in refs)),
                     "section_path":group["section_path"],"source_refs":refs,
                     "source_block_ids":list(dict.fromkeys(r["block_key"] for r in refs)),
                     "group_id":group["group_id"],"part_number":number,"part_count":len(parts),
                     "overlap_token_count":part["overlap_token_count"],"heading_context_policy":"none",
                     "text_policy":"normalized_source_only_no_added_heading_or_caption_context",
                     "tokenizer_model_id":tokenizer_config["model_id"],"tokenizer_revision":tokenizer_config["revision"],
                     "chunking_version":config["chunking_version"]}
            if group["figure_id"]:
                payload.update(figure_id=group["figure_id"],caption=group["caption"])
            if group["type"]=="figure":
                payload.update(figure_text_order=group["figure_text_order"],semantic_relations_review_status="not_reviewed",
                               boundary_approval_scope="region_boundary_only")
            if group.get("event_cause_pair_id"):
                payload["event_cause_pair_id"]=group["event_cause_pair_id"]
            payload["chunk_id"]=stable_id(base["document_id"],config["chunking_version"],group["group_id"],payload["text"],refs)
            chunks.append(payload)
            internal.append(part)
    coverage=validate_chunks(chunks,internal,sources,footers,logs,tokenizer,config)
    normalized=[]
    for key,source in sources.items():
        block=combine([u["mapped"] for u in prepared[key]])
        mapping=trace_spans(block,["primary"]*len(block.text),sources)
        for span in mapping:
            span["normalized_start"]=span.pop("chunk_start")
            span["normalized_end"]=span.pop("chunk_end")
        normalized.append({"block_key":key,"pdf_page":source["pdf_page"],"printed_page":source["printed_page"],
                           "source_block_id":source["source_block_id"],"owner":source["owner"],
                           "raw_text":source["raw_text"],"normalized_text":block.text,
                           "raw_to_normalized_map":mapping})
    packages={name:importlib.metadata.version(name) for name in ("tokenizers","huggingface-hub","PyMuPDF")}
    counts=sorted(c["token_count"] for c in chunks)
    example_multi=next(c for c in chunks if 624 in c["pdf_pages"] and 625 in c["pdf_pages"])
    examples={"multi_page":example_multi,"figure":next(c for c in chunks if c["type"]=="figure"),
              "event_cause_655":next(c for c in chunks if c.get("event_cause_pair_id"))}
    report={"body_chunks":sum(c["type"]=="body" for c in chunks),"figure_chunks":sum(c["type"]=="figure" for c in chunks),
            "token_stats":{"min":min(counts),"median":statistics.median(counts),"p95":counts[math.ceil(.95*len(counts))-1],"max":max(counts)},
            "coverage":coverage,"forced_splits":forced,"heading_uncertainties":uncertainties,
            "explicit_heading_count":len(headings),"section_hierarchy":"only_explicit_chapter_and_latest_heading_no_nested_inference",
            "normalization_counts":dict(collections.Counter((l["operation"]+":"+l.get("status","")) for l in logs)),
            "examples":examples,"packages":packages,"python_version":platform.python_version(),
            "limitations":["Figure source block/line order remains unverified; no chart values or relationships inferred.",
                           "No added heading context; section_path is deliberately flat below the explicit chapter.",
                           "Caption metadata is not automatically prepended to each figure part or sent to the model.",
                           "Sentence boundary heuristic is conservative; forced splits are logged.",
                           "Raw offsets refer to extraction block.text (Unicode code points), not raw PDF bytes."]}
    manifest={"generator_version":config["chunking_version"],"config_sha256":sha(args.config),"inputs":initial,
              "tokenizer":tokenizer_config,"packages":packages,"python_version":platform.python_version(),
              "truncation":False,"special_tokens_included":True,"embeddings_generated":False}
    for name,digest in initial.items():
        if sha(ROOT/name)!=digest:
            raise ValueError("Input mutated during chunking")
    jsonl(out/"chunks.jsonl",chunks)
    jsonl(out/"normalized_blocks.jsonl",normalized)
    jsonl(out/"normalization_log.jsonl",logs)
    save(out/"headings.json",headings)
    save(out/"report.json",report)
    manifest["chunks_sha256"]=sha(out/"chunks.jsonl")
    save(out/"run_manifest.json",manifest)
    text=["# Minimum normalization and chunking", "",f"Body chunks: {report['body_chunks']}; figure chunks: {report['figure_chunks']}.",
          f"Tokens (special tokens included): {report['token_stats']}.",f"Coverage: {coverage}.",
          "No embeddings, no added model prefix, no full-content human verification.","", "## Examples"]
    for name,chunk in examples.items():
        text.extend(["",f"### {name}: {chunk['chunk_id']}",f"PDF pages: {chunk['pdf_pages']}; tokens: {chunk['token_count']}","",chunk["text"]])
    text.extend(["","## Limitations",*['- '+s for s in report["limitations"]]])
    (out/"report.md").write_text("\n".join(text)+"\n",encoding="utf-8")
    print(f"Chunks: {report['body_chunks']} body + {report['figure_chunks']} figure; tokens {report['token_stats']}")
    print(f"Coverage passed: {coverage}; chunks SHA-256 {manifest['chunks_sha256']}")


if __name__=="__main__":
    main()
