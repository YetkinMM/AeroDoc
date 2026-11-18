"""Run one development pass against the local HTTP service."""
import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .retrieval import ROOT, dump, read, sha

URL = "http://127.0.0.1:8000"
STOP = {"budget_exceeded", "authentication", "permission_denied", "insufficient_quota",
        "connection_error", "model_unavailable", "api_key_missing_or_invalid"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blocked", choices=sorted(STOP), help="Record a failed connection probe without calling /ask")
    args = parser.parse_args()
    if not args.blocked:
        with urlopen(URL + "/health", timeout=5) as response:
            if json.load(response) != {"status": "ok", "retrieval": "bm25"}:
                raise SystemExit("Unexpected development service health")
    dataset_path = ROOT / "eval/dev_questions.json"
    questions = read(dataset_path)["questions"]
    report = {"dataset_sha256": sha(dataset_path), "endpoint": URL + "/ask", "questions": []}
    path = ROOT / "audit/answers/development.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    stop = args.blocked
    for question in questions:
        row = {key: question[key] for key in ("id", "question", "answerable")}
        if stop:
            row.update(status="not_run", reason=stop)
        else:
            request = Request(URL + "/ask", data=json.dumps({"question": question["question"]}).encode(),
                              headers={"Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=60) as response:
                    row.update(http_status=response.status, **json.load(response))
            except HTTPError as error:
                with error:
                    payload = json.load(error) if error.headers.get_content_type() == "application/json" else {}
                row.update(http_status=error.code, status="http_error")
                row.update(payload)
            except (URLError, TimeoutError):
                row.update(status="http_error", error_code="local_http_connection")
            if row.get("error_code") in STOP or row["status"] == "http_error":
                stop = row.get("error_code", "http_error")
        row["human_review"] = "pending" if row["status"] in ("answered", "insufficient_evidence") else None
        report["questions"].append(row)
        dump(path, report)
        print(row["id"], row["status"], row.get("origin", ""), row.get("error_code", ""), flush=True)
    return int(any(row["status"] not in ("answered", "insufficient_evidence")
                   for row in report["questions"]))


if __name__ == "__main__":
    raise SystemExit(main())
