"""Independent verification of serialized chunk references and repeated-run bytes."""

import argparse
import collections
import hashlib
import json
from pathlib import Path

from chunking import ModelTokenizer, stable_id

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"audit/chunking")
    parser.add_argument("--repeat",type=Path,default=ROOT/"audit/chunking_repeat")
    args=parser.parse_args()
    config=read(ROOT/"config/chunking.json")
    chunks=lines(args.output/"chunks.jsonl")
    raw={b["block_key"]:b for b in lines(args.output/"normalized_blocks.jsonl")}
    pages=lines(ROOT/config["pages_path"])
    figures=lines(ROOT/config["figures_path"])
    figure_owner={f"p{f['pdf_page']}:b{b['source_block_id']}":f["figure_id"] for f in figures for b in f.get("blocks",[])}
    captions={f["figure_id"]:next((b["text"] for b in f.get("blocks",[]) if b["text"].startswith("Figure ")),None)
              for f in figures if f["content_storage"]=="inline"}
    expected_raw={f"p{p['pdf_page']}:b{b['source_block_id']}":b["text"] for p in pages for b in p["ordered_blocks"]}
    expected_raw.update({f"p{f['pdf_page']}:b{b['source_block_id']}":b["text"] for f in figures for b in f.get("blocks",[])})
    assert {k:b["raw_text"] for k,b in raw.items()}==expected_raw
    footers={f"p{p['pdf_page']}:b{b['source_block_id']}" for p in pages for b in p["removed_footer_blocks"]}
    tokenizer=ModelTokenizer(ROOT/config["tokenizer"]["cache_dir"]/"tokenizer.json")
    primary,overlap=collections.Counter(),collections.Counter()
    primary_groups={}
    overlap_groups=[]
    for chunk in chunks:
        assert tokenizer.count(chunk["text"])==chunk["token_count"]<=500
        assert 0<=chunk["overlap_token_count"]<=50
        assert chunk["tokenizer_revision"]==config["tokenizer"]["revision"]
        assert chunk["pdf_pages"]==sorted({r["pdf_page"] for r in chunk["source_refs"]})
        assert chunk["printed_pages"]==list(dict.fromkeys(r["printed_page"] for r in chunk["source_refs"]))
        assert chunk["source_block_ids"]==list(dict.fromkeys(r["block_key"] for r in chunk["source_refs"]))
        if chunk["type"]=="figure":
            assert chunk["caption"]==captions[chunk["figure_id"]]
            assert all(figure_owner[k]==chunk["figure_id"] for k in chunk["source_block_ids"])
        else:
            assert not any(k in figure_owner for k in chunk["source_block_ids"])
        covered=collections.Counter()
        overlap_fragments=[]
        for ref in chunk["source_refs"]:
            key=ref["block_key"]
            assert key in raw and key not in footers
            assert ref["pdf_page"]==raw[key]["pdf_page"] and ref["source_block_id"]==raw[key]["source_block_id"]
            a,b=ref["raw_start"],ref["raw_end"]
            x,y=ref["chunk_start"],ref["chunk_end"]
            assert 0<=a<b<=len(raw[key]["raw_text"]) and 0<=x<y<=len(chunk["text"])
            fragment=raw[key]["raw_text"][a:b]
            actual=chunk["text"][x:y]
            assert "".join(fragment.split())=="".join(actual.split()),(chunk["chunk_id"],ref)
            covered.update(range(x,y))
            counter=primary if ref["role"]=="primary" else overlap
            counter.update((key,i) for i in range(a,b) if not raw[key]["raw_text"][i].isspace())
            for i in range(a,b):
                if not raw[key]["raw_text"][i].isspace():
                    if ref["role"]=="primary":primary_groups[(key,i)]=chunk["group_id"]
                    else:overlap_groups.append(((key,i),chunk["group_id"]))
            if ref["role"]=="overlap":
                overlap_fragments.append((x,y))
        assert all(covered[i]==1 for i,c in enumerate(chunk["text"]) if not c.isspace())
        assert all(c.isspace() for i,c in enumerate(chunk["text"]) if not covered[i])
        assert stable_id(chunk["document_id"],chunk["chunking_version"],chunk["group_id"],chunk["text"],chunk["source_refs"])==chunk["chunk_id"]
    removed=set()
    for change in lines(args.output/"normalization_log.jsonl"):
        if change.get("status")=="joined":
            key=change["block_key"]
            a,b=change["removed_raw_range"]
            assert change["support"] and raw[key]["raw_text"][a]=="-"
            removed.update((key,i) for i in range(a,b) if not raw[key]["raw_text"][i].isspace())
    expected={(k,i) for k,b in raw.items() for i,c in enumerate(b["raw_text"]) if not c.isspace()}-removed
    assert set(primary)==expected and all(v==1 for v in primary.values())
    assert all(primary_groups[position]==group for position,group in overlap_groups)
    assert {c["figure_id"] for c in chunks if c["type"]=="figure"}==set(captions)
    assert not any(c["type"]=="figure" and c.get("figure_id")=="14-37" for c in chunks)
    pairs=[c for c in chunks if c.get("event_cause_pair_id")]
    assert len({c["event_cause_pair_id"] for c in pairs})==5
    assert all(c["pdf_pages"]==[655] and "CAUSE" in c["text"] and c["type"]=="body" for c in pairs)
    # This corpus's five pairs fit whole; the general splitter can retain pair IDs over parts.
    assert len(pairs)==5 and all(c["part_count"]==1 for c in pairs)
    assert any(624 in c["pdf_pages"] and 625 in c["pdf_pages"] and
               "Proper documentation of all maintenance work" in c["text"] for c in chunks)
    headings={h["title"] for h in read(args.output/"headings.json")}
    assert all(all(title in headings for title in c["section_path"]) for c in chunks)
    assert (args.output/"chunks.jsonl").read_bytes()==(args.repeat/"chunks.jsonl").read_bytes()
    snapshot=read(ROOT/"audit/chunking/extraction_input_snapshot.json")
    assert all(sha(ROOT/name)==digest for name,digest in snapshot["protected_sha256"].items())
    result={"chunk_count":len(chunks),"source_blocks":len(raw),"primary_nonwhitespace_characters":len(primary),
            "intentional_overlap_character_copies":sum(overlap.values()),"unintentional_duplicates":0,
            "overlap_stays_in_source_group":True,"body_figure_ownership_preserved":True,
            "five_preserved_body_pairs_on_655":True,"cross_page_624_625_continuation":True,
            "two_runs_byte_identical":True,"chunks_sha256":sha(args.output/"chunks.jsonl"),
            "protected_input_files_unchanged":True,"protected_file_count":len(snapshot["protected_sha256"]),
            "special_tokens_counted":True,"truncation":False,"embeddings_generated":False}
    (args.output/"verification.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
