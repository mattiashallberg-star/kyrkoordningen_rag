from __future__ import annotations

import argparse
from pathlib import Path

from chunk_document import build_chunks_for_pdf, build_chunks_from_parsed
from utils import read_json, write_csv, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Kyrkoordningen chunks to JSONL and CSV.")
    parser.add_argument("--pdf", default="data/kyrkoordningen.pdf", help="Path to the source PDF.")
    parser.add_argument("--input", default="", help="Optional chunk JSON or parsed JSON.")
    parser.add_argument("--jsonl-output", default="output/kyrkoordningen_chunks.jsonl", help="JSONL output path.")
    parser.add_argument("--csv-output", default="output/kyrkoordningen_chunks.csv", help="CSV output path.")
    parser.add_argument("--max-tokens", type=int, default=420, help="Maximum approximate tokens per chunk.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.input:
        payload = read_json(Path(args.input))
        if "chunks" in payload:
            chunk_payload = payload
        else:
            chunk_payload = build_chunks_from_parsed(payload, max_tokens=args.max_tokens)
    else:
        chunk_payload = build_chunks_for_pdf(Path(args.pdf), max_tokens=args.max_tokens)

    chunks = chunk_payload["chunks"]
    write_jsonl(Path(args.jsonl_output), chunks)
    write_csv(Path(args.csv_output), chunks)


if __name__ == "__main__":
    main()
