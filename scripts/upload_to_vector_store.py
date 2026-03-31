from __future__ import annotations

import argparse
from pathlib import Path

from openai import OpenAI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload a local file and attach it to an OpenAI Vector Store.")
    parser.add_argument("--api-key", required=True, help="OpenAI API key.")
    parser.add_argument("--vector-store-id", required=True, help="Existing Vector Store ID.")
    parser.add_argument(
        "--file-path",
        default="output/kyrkoordningen_chunks.txt",
        help="Path to the file that should be uploaded.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = OpenAI(api_key=args.api_key)
    file_path = Path(args.file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    uploaded_file = client.files.create(file=file_path.open("rb"), purpose="assistants")
    attached = client.vector_stores.files.create(vector_store_id=args.vector_store_id, file_id=uploaded_file.id)

    print(f"uploaded_file_id={uploaded_file.id}")
    print(f"vector_store_file_id={attached.id}")
    print(f"vector_store_id={args.vector_store_id}")


if __name__ == "__main__":
    main()
