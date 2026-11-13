"""Download only checksum-pinned BGE tokenizer/config files, never model weights."""

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((ROOT/"config/chunking.json").read_text(encoding="utf-8"))["tokenizer"]
    directory = ROOT/config["cache_dir"]
    directory.mkdir(parents=True,exist_ok=True)
    for name, expected in config["files"].items():
        path = directory/name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==expected:
            continue
        url = f"https://huggingface.co/{config['model_id']}/resolve/{config['revision']}/{name}"
        data = urllib.request.urlopen(url,timeout=60).read()
        if hashlib.sha256(data).hexdigest()!=expected:
            raise ValueError(f"Tokenizer artifact hash mismatch: {name}")
        path.write_bytes(data)
    print(f"Pinned tokenizer ready: {config['model_id']} @ {config['revision']}")


if __name__=="__main__":
    main()
