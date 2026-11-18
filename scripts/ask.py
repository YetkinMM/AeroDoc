"""Ask a grounded question or make one short structured connection probe."""
import argparse
import json

from .answering import create_service, normalize_question


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--retrieval", choices=["bm25", "bge"])
    args = parser.parse_args()
    if args.probe == (args.question is not None):
        parser.error("Supply one question or --probe")
    try:
        question = normalize_question(args.question) if not args.probe else "What is the answer?"
    except ValueError as error:
        parser.error(str(error))
    result = create_service(args.retrieval).ask(question, probe=args.probe)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return int(result["status"] not in ("answered", "insufficient_evidence"))


if __name__ == "__main__":
    raise SystemExit(main())
