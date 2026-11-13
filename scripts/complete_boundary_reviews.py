"""Record group approvals, choose unique preferred regions, and inspect page 655.

Review artifacts only. No production extractor/config/source output modifications.
"""

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from extract_corpus import event_cause_pairs

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit/figure_region_candidates"
REV = OUT / "boundary_review_completion"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if REV.exists():
        raise SystemExit("Completion revision exists; preserve history.")
    REV.mkdir()
    cp, ap, lp = OUT/"figure_regions.candidates.json", OUT/"boundary_approvals.json", OUT/"checklist.json"
    old_data, old_ledger, checklist = read(cp), read(ap), read(lp)
    data, ledger = copy.deepcopy(old_data), copy.deepcopy(old_ledger)
    for name,obj in (("candidates.before.json",old_data),("approvals.before.json",old_ledger),("checklist.before.json",checklist)):
        write(REV/name,obj)
    allowed = {cp,ap,lp,OUT/"boundary_approvals.md",OUT/"checklist.md",OUT/"pending_review_groups/index.md"}
    paths = {p for folder in ("scripts","config","eval","docs","audit") for p in (ROOT/folder).rglob("*")
             if p.is_file() and p not in allowed and REV not in p.parents}
    protected = {p.relative_to(ROOT).as_posix():sha(p) for p in paths}
    write(REV/"protected_before.json",protected)
    groups = read(OUT/"pending_review_groups/index.json")["groups"]
    approved_ids = {a["candidate_id"] for a in ledger["approvals"]}
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    additions = []
    for group in groups:
        for ref in group["regions"]:
            if group["group"] == 12 and ref["pdf_page"] != 652:
                continue  # No user approval of the 655 boundary inferred.
            r = next(r for r in data["regions"] if r["candidate_id"]==ref["candidate_id"])
            assert r["bbox"] == ref["bbox"]
            assert r["candidate_id"] not in approved_ids
            entry = {"candidate_id":r["candidate_id"],"pdf_page":r["pdf_page"],"figure_id":r["figure_id"],
                     "bbox":copy.deepcopy(r["bbox"]),"origin":r["origin"],"review_status":"human_verified",
                     "approval_scope":"region_boundary_only","accepted":True,"recorded_at_utc":stamp,
                     "reviewed_by":"user","evidence":"Explicit user approval of Groups 01-11 and PDF 652 in Group 12.",
                     "source_group":group["group"],
                     "source_overlay":"audit/figure_region_candidates/pending_review_groups/"+group["preview_file"],
                     "source_overlay_sha256":sha(OUT/"pending_review_groups"/group["preview_file"]),
                     "text_order_review_status":"not_reviewed","semantic_relations_review_status":"not_reviewed"}
            additions.append(entry)
            r.update({"review_status":"human_verified","accepted":True,"acceptance_scope":"region_boundary_only",
                      "boundary_approval":entry,"text_order_review_status":"not_reviewed","semantic_relations_review_status":"not_reviewed"})
            r["notes"].append("User approved boundary only via review group; internal order/semantic relations remain unreviewed.")
    ledger["approvals"].extend(additions)
    ledger["last_updated_at_utc"] = stamp
    ledger["note"] = "39 approved boundary records; one preferred record per figure selected separately. PDF 655 boundary awaits user review."
    assert ledger["approvals"][:len(old_ledger["approvals"])] == old_ledger["approvals"]
    assert len(ledger["approvals"])==39
    config = read(ROOT/"config/corpus.json")
    pdf_path = ROOT/config["pdf_path"]
    assert sha(pdf_path)==data["source_sha256"]
    r655 = next(r for r in data["regions"] if r["pdf_page"]==655)
    original655 = copy.deepcopy(r655)
    with pymupdf.open(pdf_path) as doc:
        page = doc[654]
        blocks = [{"id":b[5],"bbox":list(b[:4]),"text":b[4]} for b in page.get_text("blocks",sort=False) if b[6]==0]
        incident = next(b for b in blocks if b["text"].strip()=="INCIDENT")
        rect = pymupdf.Rect(r655["bbox"])
        assert rect.contains(pymupdf.Rect(incident["bbox"]))
        nonfooter = [b for b in blocks if b["bbox"][1]<720]
        assert all(rect.contains(pymupdf.Rect(b["bbox"])) for b in nonfooter)
        assert len(nonfooter)==21
        corpus = next(json.loads(line) for line in (ROOT/"audit/corpus/pages.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(line)["pdf_page"]==655)
        ordered = sorted(nonfooter,key=lambda b:(b["bbox"][1],b["bbox"][0]))
        text = "\n\n".join(b["text"].strip() for b in ordered)+"\n"
        assert text == corpus["text"]
        pairs = event_cause_pairs(text)
        assert len(pairs)==5
        headings = [b["text"].strip() for b in ordered if b["text"].strip() in ("INCIDENT","ACCIDENT","CAUSE")]
        assert headings == ["INCIDENT","CAUSE","INCIDENT","CAUSE","ACCIDENT","CAUSE","ACCIDENT","CAUSE","ACCIDENT","CAUSE"]
        page.get_pixmap(dpi=140,alpha=False).save(REV/"page_655.original.png")
        page.get_pixmap(dpi=180,alpha=False,clip=pymupdf.Rect(48,37,554,167)).save(REV/"page_655.original.top.png")
        overlay = pymupdf.open()
        overlay.insert_pdf(doc,from_page=654,to_page=654)
        canvas = overlay[0]
        canvas.draw_rect(rect,color=(1,0,0),width=1,overlay=True)
        # Put all review text above the region, away from the first INCIDENT.
        canvas.insert_text((10,12),"PDF 655 | boundary awaiting user review | preserve_in_body",fontsize=8,overlay=True)
        canvas.insert_text((54,33),"P655-A01 / Figure 14-37 -- label outside figure",fontsize=8,color=(1,0,0),overlay=True)
        canvas.get_pixmap(dpi=140,alpha=False).save(REV/"page_655.heading_visible.overlay.png")
        overlay.close()
    r655.update({"review_status":"agent_reviewed","accepted":False,"boundary_review_scope":"region_boundary_only",
                 "text_order_review_status":"not_reviewed","semantic_relations_review_status":"not_reviewed"})
    r655["notes"].append("Source first INCIDENT is inside unchanged bbox; old overlay ID label obscured it. New overlay moves label above region. All 21 nonfooter blocks and five event/cause pairs retained; preserve_in_body. User boundary approval still pending.")
    assert r655["intended_handling"]=="preserve_in_body" and r655["bbox"]==original655["bbox"]
    selections = []
    for key in sorted({(r["pdf_page"],r["figure_id"]) for r in data["regions"]}):
        alternatives = [r for r in data["regions"] if (r["pdf_page"],r["figure_id"])==key]
        selected = next((r for r in alternatives if r["origin"]=="manual"),alternatives[0]) if key[0] in (625,636,645) else alternatives[0]
        for r in alternatives:
            r["preferred_candidate_id"] = selected["candidate_id"]
            r["selected_for_future_extraction"] = r is selected and r["accepted"]
            r["selection_status"] = "awaiting_boundary_approval" if not r["accepted"] else ("preferred" if r is selected else "approved_alternative_not_selected")
        selections.append({"pdf_page":key[0],"figure_id":key[1],"preferred_candidate_id":selected["candidate_id"],
                           "bbox":selected["bbox"],"intended_handling":selected["intended_handling"],
                           "boundary_accepted":selected["accepted"],"alternative_candidate_ids":[r["candidate_id"] for r in alternatives if r is not selected],
                           "eligible_for_future_extraction":selected["accepted"]})
    assert len(selections)==37 and sum(s["eligible_for_future_extraction"] for s in selections)==36
    assert [s["preferred_candidate_id"] for s in selections if s["pdf_page"] in (625,636,645)]==["P625-M01","P636-M01","P645-M01"]
    selection_file = {"document_id":data["document_id"],"source_sha256":data["source_sha256"],
                      "scope":"region_boundary_only","applied_to_extraction":False,"regions":selections}
    report655 = {"pdf_page":655,"candidate_id":r655["candidate_id"],"bbox":r655["bbox"],"bbox_changed":False,
                 "first_incident_block":incident,"header_inside_region":True,
                 "cause":"Old overlay ID label covered the first heading; not clipping or extraction loss.",
                 "all_21_nonfooter_blocks_inside":True,"heading_sequence":headings,"five_pairs":pairs,
                 "matches_existing_body_text_exactly":True,"intended_handling":"preserve_in_body",
                 "review_status":"agent_reviewed","accepted":False,"human_text_order_verified":False,
                 "semantic_relations_verified":False,
                 "new_overlay":"audit/figure_region_candidates/boundary_review_completion/page_655.heading_visible.overlay.png"}
    write(REV/"page_655.check.json",report655)
    write(OUT/"region_selection.json",selection_file)
    write(cp,data)
    write(ap,ledger)
    for row in checklist:
        rs = [r for r in data["regions"] if r["pdf_page"]==row["pdf_page"]]
        row["boundary_approved_candidate_ids"] = [r["candidate_id"] for r in rs if r["accepted"]]
        row["pending_candidate_ids"] = [r["candidate_id"] for r in rs if not r["accepted"]]
        row["region_review_statuses"] = {r["candidate_id"]:r["review_status"] for r in rs}
        if rs:
            row["review_scope"] = "region_boundary_only"
            row["review_status"] = "human_verified" if all(r["accepted"] for r in rs) else "agent_reviewed"
        if row["pdf_page"]==655:
            row["overlay_path"] = report655["new_overlay"]
            row["required_check"] = "Only remaining boundary approval: first INCIDENT now visible; unchanged bbox, preserve_in_body."
        elif rs:
            row["required_check"] = "Boundary accepted only; internal order/semantics remain unreviewed."
    write(lp,checklist)
    lines = ["# Bölge sınırı onayları", "", "Kapsam yalnız region_boundary_only; iç sıra ve anlam ilişkileri doğrulanmadı.",
             "39 onaylı sınır kaydı, 36 tekil onaylı şekil. 655 kullanıcı sınır onayı bekliyor.", "",
             "| Kimlik | PDF | Figure | Tam bbox | Gelecek extraction seçimi |", "|---|---|---|---|---|"]
    for r in data["regions"]:
        if r["accepted"]:
            lines.append(f"| {r['candidate_id']} | {r['pdf_page']} | {r['figure_id']} | {r['bbox']} | {r['selection_status']} |")
    (OUT/"boundary_approvals.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (OUT/"checklist.md").write_text("# Çözümlenmemiş sınır onayı\n\nYalnız PDF 655 / P655-A01 kullanıcı sınır onayı bekliyor. Diğer aday sınırlarının onayları boundary_approvals.json içinde.\n\n[655: başlık görünür overlay](boundary_review_completion/page_655.heading_visible.overlay.png)\n\n625, 636 ve 645 için manuel bölgeler tercih edildi. Alternatifler region_selection.json içinde işlenmeyecek olarak kaydedildi.\n\nİç sıra ve anlam ilişkileri bu onayların kapsamı dışındadır. Extraction değişmedi.\n",encoding="utf-8")
    index = OUT/"pending_review_groups/index.md"
    index.write_text("# Önceki görsel inceleme grupları\n\nGrup 01–11 ve Grup 12 içindeki 652'nin sınırları kullanıcı tarafından kabul edildi. Eski grup PDF/PNG dosyaları tarihsel inceleme materyali olarak korunuyor.\n\nYalnız [655'in yeni görüntüsü](../boundary_review_completion/page_655.heading_visible.overlay.png) kullanıcı sınır onayı bekliyor.\n\n[Kimlik ve bbox içeren onaylar](../boundary_approvals.md) · [Tekil bölge seçimi](../region_selection.json)\n",encoding="utf-8")
    changed = [name for name,h in protected.items() if sha(ROOT/name)!=h]
    assert not changed,changed
    write(REV/"validation.json",{"approved_boundary_records":39,"approved_unique_figures":36,"preferred_manual_ids":["P625-M01","P636-M01","P645-M01"],
          "unresolved_boundary_ids":["P655-A01"],"protected_file_count":len(protected),"protected_files_changed":changed,
          "extraction_applied":False,"config_figure_regions_created":False,"internal_text_order_verified":False,"semantic_relations_verified":False})
    print(f"Recorded 29 new approvals; 39 approved records total. Preferred unique figures: 36. Remaining: P655-A01.")
    print(f"655 first INCIDENT bbox: {incident['bbox']}; region top: {r655['bbox'][1]}; inside: True. Overlay label moved; bbox unchanged.")


if __name__ == "__main__":
    main()
