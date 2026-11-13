"""Rebuild the reviewed AeroDoc dev-v0.1 question set.

Place this file in scripts/ and run it with the project's Python environment.
The input labels below are the reviewed questions, answers, and evidence.
"""

import argparse
import hashlib
import json
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "eval" / "dev_questions.json"
DATASET_VERSION = "dev-v0.1"
CORPUS_VERSION = "v0.1"
SOURCE = {'document_id': 'faa_amt_general_30b_2023',
 'pdf_sha256': '0a39c01bbc454e77a49813cf27e2ef291756fa7111d9308bc290cd0eb71616fd',
 'pdf_pages': {'start': 624, 'end': 655},
 'page_numbering': 'one_based_inclusive'}

# The human review flags are part of the input, just like the answer labels.
REVIEWED_QUESTIONS = [{'id': 'D01',
  'question': 'What is the difference between omission, commission, and extraneous errors?',
  'answerable': True,
  'evidence_quote': [{'pdf_page': 624, 'text': 'Omission: not performing an act or task.'},
                     {'pdf_page': 624, 'text': 'Commission: accomplishing a task incorrectly.'},
                     {'pdf_page': 624, 'text': 'Extraneous: performing a task not authorized.'}],
  'reference_answer': 'An omission is failing to perform a task. A commission error is '
                      'performing a task incorrectly. An extraneous error is performing an '
                      'unauthorized task.',
  'question_type': 'definition',
  'verified_by_human': True},
 {'id': 'D02',
  'question': 'Why can maintenance errors be harder to detect than pilot errors?',
  'answerable': True,
  'evidence_quote': [{'pdf_page': 624,
                      'text': 'Although pilot/co-pilot errors tend to have immediate and highly '
                              'visible effects, maintenance errors tend to be more latent and '
                              'less obvious.'}],
  'reference_answer': 'Maintenance errors can remain latent and less visible, while pilot errors '
                      'tend to have immediate and visible effects.',
  'question_type': 'comparison',
  'verified_by_human': True},
 {'id': 'D03',
  'question': 'What makes an AMT’s working environment demanding, and how much time can '
              'documentation take compared with hands-on work?',
  'answerable': True,
  'evidence_quote': [{'pdf_page': 624,
                      'text': 'They can be working in the evening or early morning hours, in '
                              'confined spaces, on high platforms, and in a variety of adverse '
                              'temperature/humidity conditions. The work can be physically '
                              'strenuous, yet it also requires attention to detail.'},
                     {'pdf_page': 625,
                      'text': 'AMTs typically spend as much time updating maintenance logs as '
                              'they do performing the work.'}],
  'reference_answer': 'AMTs may work evenings or early mornings, in confined spaces, on high '
                      'platforms, and in adverse temperature or humidity conditions. The work '
                      'can be physically demanding and requires attention to detail. They '
                      'typically spend as much time updating maintenance logs as performing the '
                      'work itself.',
  'question_type': 'multi_page',
  'verified_by_human': True},
 {'id': 'D04',
  'question': 'How does the handbook classify accidentally transposing a torque value from 26 to '
              '62, compared with knowingly deviating from a procedure?',
  'answerable': True,
  'evidence_quote': [{'pdf_page': 636,
                      'text': 'For example, an AMT reads the torque values from a job card and '
                              'unintentionally transposed the number 26 to 62.'},
                     {'pdf_page': 636,
                      'text': 'If someone knowingly or intentionally chooses to do something '
                              'wrong, it is a violation, which means that one has purposely '
                              'deviated from safe practices, procedures, standards, or '
                              'regulations.'}],
  'reference_answer': 'Accidentally transposing 26 to 62 is an unintentional error. Knowingly '
                      'deviating from a procedure is a violation.',
  'question_type': 'classification',
  'verified_by_human': True},
 {'id': 'D05',
  'question': 'According to the handbook’s broken-ladder example, what are the active and latent '
              'errors?',
  'answerable': True,
  'evidence_quote': [{'pdf_page': 636,
                      'text': 'In this example, the active error was falling from the ladder. '
                              'The latent error was the broken ladder that someone should have '
                              'replaced.'}],
  'reference_answer': 'In the handbook’s example, the active error was falling from the ladder. '
                      'The latent error was the broken ladder that someone should have replaced.',
  'question_type': 'example_analysis',
  'verified_by_human': True},
 {'id': 'D06',
  'question': 'How can AMTs respond to self-induced pressure and unrealistic repair deadlines?',
  'answerable': True,
  'evidence_quote': [{'pdf_page': 645,
                      'text': 'In an effort to combat self-induced pressure, technicians should '
                              'ask for help if they feel overwhelmed and under a time constraint '
                              'to complete a repair. Another method is to have someone check the '
                              'repair thoroughly to ensure that all maintenance tasks were '
                              'completed correctly.'},
                     {'pdf_page': 645,
                      'text': 'Lastly, if given a repair with a specific time limitation that '
                              'you feel is unrealistic or compromises safety, bring it to the '
                              'attention of the organization’s management and openly discuss a '
                              'different course of action.'}],
  'reference_answer': 'Technicians can ask for help when overwhelmed by time pressure or have '
                      'another person check the repair thoroughly. If the deadline is '
                      'unrealistic or compromises safety, they should raise it with management '
                      'and discuss a different course of action.',
  'question_type': 'recommended_response',
  'verified_by_human': True},
 {'id': 'D07',
  'question': 'According to the handbook, what percentage of aviation accidents result from '
              'human error, and what percentage of those accidents are maintenance-related?',
  'answerable': True,
  'evidence_quote': [{'pdf_page': 624,
                      'text': 'A review of accident related data indicates that approximately '
                              '75–80 percent of all aviation accidents are the result of human '
                              'error. Of those accidents, about 12 percent are maintenance '
                              'related.'}],
  'reference_answer': 'According to the handbook, approximately 75–80% of all aviation accidents '
                      'result from human error. About 12% of those human-error accidents are '
                      'maintenance-related.',
  'question_type': 'numeric',
  'verified_by_human': True},
 {'id': 'D08',
  'question': 'How does the handbook define assertiveness?',
  'answerable': True,
  'evidence_quote': [{'pdf_page': 645,
                      'text': 'Assertiveness is the ability to express your feelings, opinions, '
                              'beliefs, and needs in a positive, productive manner and should '
                              'not be confused with being aggressive.'}],
  'reference_answer': 'Assertiveness means expressing your feelings, opinions, beliefs, and '
                      'needs in a positive, productive way.',
  'question_type': 'definition',
  'verified_by_human': True},
 {'id': 'D09',
  'question': 'What exact torque value should be used when replacing the forward elevator trim '
              'cable on a Beech 1900D?',
  'answerable': False,
  'evidence_quote': [],
  'reference_answer': 'The Human Factors chapter describes the accident but does not specify a '
                      'torque value for replacing the forward elevator trim cable.',
  'question_type': 'missing_specification',
  'verified_by_human': True},
 {'id': 'D10',
  'question': 'What is the current METAR report for London Gatwick Airport?',
  'answerable': False,
  'evidence_quote': [],
  'reference_answer': 'The selected handbook chapter does not provide current METAR reports for '
                      'London Gatwick Airport.',
  'question_type': 'out_of_scope_current_data',
  'verified_by_human': True}]


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read {path}: {exc}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_source() -> tuple[Path, int]:
    """Check that the project uses the PDF and scope reviewed for this set."""
    config = read_json(ROOT / "config" / "corpus.json")
    expected_config = {
        "corpus_version": CORPUS_VERSION,
        "document_id": SOURCE["document_id"],
        "page_ranges": [SOURCE["pdf_pages"]],
        "page_numbering": SOURCE["page_numbering"],
    }
    for field, expected in expected_config.items():
        if config.get(field) != expected:
            raise SystemExit(
                f"config/corpus.json: {field} must be {expected!r} "
                f"to rebuild {DATASET_VERSION}."
            )

    pdf_path = ROOT / config["pdf_path"]
    if not pdf_path.is_file():
        raise SystemExit(f"Place the source PDF at {pdf_path}")

    actual_hash = sha256(pdf_path)
    if actual_hash != SOURCE["pdf_sha256"]:
        raise SystemExit("The source PDF SHA-256 differs from the reviewed copy.")

    manifest = read_json(pdf_path.with_name("manifest.json"))
    if actual_hash != manifest.get("sha256"):
        raise SystemExit("The source PDF SHA-256 differs from manifest.json.")

    return pdf_path, config["expected_page_count"]


def build_dataset(pdf_path: Path, expected_page_count: int) -> dict:
    """Check the evidence on each cited PDF page and assemble the output."""
    cited_pages = {
        item["pdf_page"]
        for question in REVIEWED_QUESTIONS
        for item in question["evidence_quote"]
    }
    page_range = SOURCE["pdf_pages"]
    if any(not page_range["start"] <= page <= page_range["end"] for page in cited_pages):
        raise SystemExit("An evidence page is outside the reviewed chapter.")

    with pymupdf.open(pdf_path) as document:
        if document.page_count != expected_page_count:
            raise SystemExit(
                f"Expected {expected_page_count} PDF pages, found {document.page_count}."
            )
        # The questions use 1-based page numbers. PyMuPDF uses 0-based indexes.
        page_text = {
            page: " ".join(document[page - 1].get_text().split())
            for page in cited_pages
        }

    records = []
    for question in REVIEWED_QUESTIONS:
        evidence = question["evidence_quote"]
        if question["answerable"] != bool(evidence):
            raise SystemExit(f"{question['id']}: answerable label and evidence disagree.")

        for item in evidence:
            page = item["pdf_page"]
            quote = " ".join(item["text"].split())
            if not quote or quote not in page_text[page]:
                raise SystemExit(f"{question['id']}: quote not found on PDF page {page}.")

        records.append({
            "id": question["id"],
            "question": question["question"],
            "answerable": question["answerable"],
            "source_pages": sorted({item["pdf_page"] for item in evidence}),
            "evidence_quote": evidence,
            "reference_answer": question["reference_answer"],
            "question_type": question["question_type"],
            "verified_by_human": question["verified_by_human"],
            "corpus_version": CORPUS_VERSION,
        })

    return {
        "dataset_version": DATASET_VERSION,
        "split": "development",
        "source": SOURCE,
        "questions": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output JSON path (default: eval/dev_questions.json in the project).",
    )
    output = parser.parse_args().output

    pdf_path, expected_page_count = load_source()
    dataset = build_dataset(pdf_path, expected_page_count)
    text = json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"

    if output.exists():
        if output.read_text(encoding="utf-8-sig") != text:
            raise SystemExit(
                f"{output} already contains a different file. "
                "Use --output to write a separate copy."
            )
        print(f"Already up to date: {output}")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        print(f"Wrote: {output}")

    questions = dataset["questions"]
    quotes = sum(len(record["evidence_quote"]) for record in questions)
    print(f"Questions: {len(questions)}. Evidence quotes checked: {quotes}.")
    print(f"SHA-256: {sha256(output)}")


if __name__ == "__main__":
    main()
