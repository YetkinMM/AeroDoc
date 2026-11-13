"""Record explicitly approved boundary geometry; prepare pending review groups.

No detection or extraction is run. Text order and semantic relations stay unreviewed.
"""

import copy
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from build_figure_region_candidates import label

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit/figure_region_candidates"
REVIEW = OUT / "pending_review_groups"
APPROVED_PAGES = (635, 636, 647, 653, 654)
EXPECTED_IDS = {"P635-A01", "P635-A02", "P636-A01", "P636-M01", "P647-A01",
                "P653-A01", "P653-A02", "P653-A03", "P653-A04", "P654-A01"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    if REVIEW.exists() or (OUT / "boundary_approvals.json").exists():
        raise SystemExit("Approval/review package exists; preserve review history.")
    REVIEW.mkdir()
    candidate_path, checklist_path = OUT / "figure_regions.candidates.json", OUT / "checklist.json"
    original, checklist = read(candidate_path), read(checklist_path)
    data = copy.deepcopy(original)
    write(REVIEW / "candidates.before_approval.json", original)
    write(REVIEW / "checklist.before_approval.json", checklist)
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"],cwd=ROOT,encoding="utf-8").splitlines()
    protected_paths = {ROOT / name for name in names}
    protected_paths.update(p for p in (ROOT / "audit").rglob("*") if p.is_file()
                           and REVIEW not in p.parents and p not in (candidate_path, checklist_path, OUT / "checklist.md"))
    protected = {p.relative_to(ROOT).as_posix():sha(p) for p in protected_paths if p.is_file()}
    write(REVIEW / "initial_state.json", {"protected_sha256":protected,
          "git_status":subprocess.check_output(["git","status","--short","--branch"],cwd=ROOT,encoding="utf-8")})
    config = read(ROOT / "config/corpus.json")
    pdf_path = ROOT / config["pdf_path"]
    assert sha(pdf_path) == data["source_sha256"]
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    approvals = []
    for region in data["regions"]:
        if region["candidate_id"] not in EXPECTED_IDS:
            continue
        n = region["pdf_page"]
        if n == 653:
            assert region["figure_id"] not in ("14-32", "14-35") or region["bbox"] == ({"14-32":[53,44,295,324],"14-35":[300,309,548,564]}[region["figure_id"]])
        overlay = "page_653.corrected.overlay.png" if n == 653 else f"page_{n}.overlay.png"
        # Bind the approval to geometry actually drawn in the earlier package.
        source = read(OUT / "page_653_manual_review/candidates.before.json") if n == 653 else None
        if n != 653:
            old_probe = read(ROOT / f"audit/figure_region_probe/iteration_2_page_{n}.json")
            expected_boxes = [r["bbox"] for r in old_probe["evaluation"]["regions"]]
            if region["origin"] == "manual":
                expected_boxes.append(config["audit"]["figure_regions_by_page"][str(n)])
            assert region["bbox"] in expected_boxes
        entry = {"candidate_id":region["candidate_id"], "pdf_page":n, "figure_id":region["figure_id"],
                 "bbox":copy.deepcopy(region["bbox"]), "origin":region["origin"],
                 "review_status":"human_verified", "approval_scope":"region_boundary_only",
                 "accepted":True, "recorded_at_utc":stamp, "reviewed_by":"user",
                 "evidence":"Explicit boundary acceptance in this conversation; no text-order or semantic approval.",
                 "source_overlay":"audit/figure_region_candidates/"+overlay,
                 "source_overlay_sha256":sha(OUT / overlay),
                 "text_order_review_status":"not_reviewed", "semantic_relations_review_status":"not_reviewed"}
        if n == 636:
            entry["alternative_group"] = "PDF636-Figure14-16"
            entry["activation_note"] = "Both displayed geometries approved as alternatives; do not activate overlapping regions together."
        approvals.append(entry)
        region.update({"review_status":"human_verified", "accepted":True,
                       "acceptance_scope":"region_boundary_only", "boundary_approval":entry,
                       "text_order_review_status":"not_reviewed", "semantic_relations_review_status":"not_reviewed"})
        region["notes"].append("User explicitly accepted this bbox only. Internal text order and semantic relations are NOT verified.")
    assert {a["candidate_id"] for a in approvals} == EXPECTED_IDS
    for old,new in zip(original["regions"],data["regions"]):
        if old["candidate_id"] not in EXPECTED_IDS:
            assert old == new
        assert old["bbox"] == new["bbox"]
    data["acceptance_status"] = "partially_accepted_boundaries_only"
    ledger = {k:data[k] for k in ("document_id","source_sha256","pymupdf_version","coordinate_system")}
    ledger.update({"scope":"region_boundary_only", "recorded_at_utc":stamp, "approvals":approvals,
                   "internal_text_order_verified":False, "semantic_relations_verified":False,
                   "accepted_config_created":False,
                   "note":"636 contains two approved alternative geometries; no active config selected."})
    pending = [r for r in data["regions"] if not r.get("accepted",False)]
    pages = sorted({r["pdf_page"] for r in pending})
    groups = []
    with pymupdf.open(pdf_path) as source_pdf:
        for offset in range(0,len(pages),2):
            group_pages = pages[offset:offset+2]
            number = offset//2+1
            stem = f"group_{number:02}_pdf_"+"_".join(map(str,group_pages))
            group_doc = pymupdf.open()
            for n in group_pages:
                group_doc.insert_pdf(source_pdf,from_page=n-1,to_page=n-1)
                page = group_doc[-1]
                row = next(row for row in checklist if row["pdf_page"] == n)
                page.draw_rect(pymupdf.Rect(0,0,page.rect.width,20),color=None,fill=(1,1,1),overlay=True)
                title = f"GROUP {number:02} | PDF {n} / printed {row['printed_page']} | PENDING BOUNDARIES"
                page.insert_text((8,12),title,fontsize=8,overlay=True)
                for region in pending:
                    if region["pdf_page"] == n:
                        label(page,region,(0,0.5,0) if region["origin"] == "manual" else (1,0,0),bottom=region["origin"] == "manual")
                page.insert_text((8,19),"RED auto / GREEN manual comparison; neither color means approval. Internal order not reviewed.",fontsize=5,overlay=True)
            group_doc.save(REVIEW / (stem+".pdf"))
            # Native-size PDF pages are kept intact. Preview places two pages
            # side by side at 110 DPI, rather than shrinking to thumbnails.
            sheet_doc = pymupdf.open()
            sheet = sheet_doc.new_page(width=594*len(group_pages),height=774)
            for i in range(len(group_pages)):
                sheet.show_pdf_page(pymupdf.Rect(i*594,0,(i+1)*594,774),group_doc,i)
            sheet.get_pixmap(dpi=110,alpha=False).save(REVIEW/(stem+".png"))
            sheet_doc.close()
            group_doc.close()
            entries = [r for r in pending if r["pdf_page"] in group_pages]
            groups.append({"group":number,"pdf_pages":group_pages,"pdf_file":stem+".pdf","preview_file":stem+".png",
                           "regions":[{k:r[k] for k in ("candidate_id","pdf_page","figure_id","bbox","origin","review_status","intended_handling")} for r in entries]})
            print(f"Group {number:02}: {group_pages}, {len(entries)} pending regions",flush=True)
    for row in checklist:
        page_regions = [r for r in data["regions"] if r["pdf_page"] == row["pdf_page"]]
        row["boundary_approved_candidate_ids"] = [r["candidate_id"] for r in page_regions if r.get("accepted")]
        row["pending_candidate_ids"] = [r["candidate_id"] for r in page_regions if not r.get("accepted")]
        row["region_review_statuses"] = {r["candidate_id"]:r["review_status"] for r in page_regions}
        if row["pdf_page"] in APPROVED_PAGES:
            row["review_status"] = "human_verified"
            row["review_scope"] = "region_boundary_only"
            row["required_check"] = "Boundary accepted by user only; internal text order and semantic relations remain unreviewed."
    write(candidate_path,data)
    write(OUT / "boundary_approvals.json",ledger)
    write(checklist_path,checklist)
    write(REVIEW / "index.json",{"document_id":data["document_id"],"source_sha256":data["source_sha256"],
                                "group_size_pdf_pages":2,"pending_region_count":len(pending),"groups":groups})
    lines = ["# Kalan bölge sınırları: görsel inceleme grupları", "",
             "Her PDF iki tam boyutlu sayfa içerir; yakınlaştırarak okuyabilirsiniz. PNG yan yana 110 DPI önizlemedir.",
             "Kırmızı: otomatik aday; yeşil: manuel karşılaştırma. Bu gruplardaki tüm bölgeler pending.",
             "İnceleme yalnız sınır/kapsam içindir; metin sırası ve anlam ilişkileri ayrıca açık kalır.", "",
             "| Grup | PDF sayfaları | Bölgeler | Yakınlaştırılabilir PDF | PNG |", "|---|---|---|---|---|"]
    for group in groups:
        ids = ", ".join(r["candidate_id"]+" ("+r["figure_id"]+")" for r in group["regions"])
        lines.append(f"| {group['group']:02} | {', '.join(map(str,group['pdf_pages']))} | {ids} | [PDF]({group['pdf_file']}) | [PNG]({group['preview_file']}) |")
    lines.extend(["", "636'nın iki onaylı sınırı aynı şekil için alternatiflerdir; bu paket onları yeniden incelemeye sunmaz.",
                  "625 ve 645'in otomatik ve manuel sınırları henüz pending alternatifler olarak birlikte gösterilir.",
                  "655'te beş olay–neden çiftinin tamamı korunmalı; intended_handling=preserve_in_body.",
                  "624, 632 ve 639'da aday bölge yoktur; bu sayfalar bu onayla doğrulanmış sayılmaz.",
                  "Bu dosyalar eski overlay'lerin yerine geçmez. Önceki overlay başlıklarındaki pending bilgisi üretim anına aittir."])
    (REVIEW / "index.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    # Keep original diagnostics/checklist entries as history; make current approval scope explicit.
    md_path = OUT / "checklist.md"
    text = md_path.read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if not line.startswith("Current boundary approval status:"))
    text += "\n\nCurrent boundary approval status: 10 region boundaries on PDF 635, 636, 647, 653, 654 explicitly accepted by user. Text order/semantics NOT verified. See [boundary approvals](boundary_approvals.json) and [pending groups](pending_review_groups/index.md). Earlier entries above describe the initial review state.\n"
    md_path.write_text(text,encoding="utf-8")
    changed = [name for name,h in protected.items() if sha(ROOT/name) != h]
    assert not changed, changed
    write(REVIEW / "validation.json",{"accepted_boundary_records":len(approvals),"unique_accepted_figures":len({(a['pdf_page'],a['figure_id']) for a in approvals}),
          "pending_regions":len(pending),"pending_pages":len(pages),"review_groups":len(groups),
          "protected_file_count":len(protected),"protected_files_changed":changed,
          "bbox_values_changed":False,"internal_text_order_verified":False,"semantic_relations_verified":False})
    print(f"Recorded {len(approvals)} boundary approvals; {len(pending)} pending regions; protected files unchanged.")


if __name__ == "__main__":
    main()
