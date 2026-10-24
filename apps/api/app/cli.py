"""Beginner-friendly local import commands. Run with: python -m app.cli."""

import argparse
from pathlib import Path

from app.config import get_database_path
from app.import_service import import_directory
from app.knowledge_store import (
    create_knowledge_base,
    list_active_chunks,
    list_documents,
    list_knowledge_bases,
)
from app.retrieval import search_knowledge_base


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Knowledge Assistant local importer")
    parser.add_argument("--db", type=Path, default=get_database_path())
    commands = parser.add_subparsers(dest="command", required=True)

    kb = commands.add_parser("kb", help="Manage knowledge bases")
    kb_commands = kb.add_subparsers(dest="kb_command", required=True)
    create = kb_commands.add_parser("create")
    create.add_argument("--name", required=True)
    kb_commands.add_parser("list")

    document_import = commands.add_parser("import", help="Import a selected folder")
    document_import.add_argument("--kb", required=True)
    document_import.add_argument("--dir", type=Path, required=True)
    document_import.add_argument(
        "--originals",
        choices=("copy", "skip"),
        default="copy",
        help="copy (default) stores exact source bytes; skip stores parsed text only",
    )

    documents = commands.add_parser("docs", help="Inspect imported documents")
    docs_commands = documents.add_subparsers(dest="docs_command", required=True)
    listing = docs_commands.add_parser("list")
    listing.add_argument("--kb", required=True)

    chunks = commands.add_parser("chunks", help="Inspect stored text chunks")
    chunk_commands = chunks.add_subparsers(dest="chunks_command", required=True)
    chunk_listing = chunk_commands.add_parser("list")
    chunk_listing.add_argument("--kb", required=True)

    search = commands.add_parser("search", help="Try keyword retrieval locally")
    search.add_argument("--kb", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=5)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "kb" and args.kb_command == "create":
            kb_id = create_knowledge_base(args.db, args.name)
            print(f"Created knowledge base: {kb_id}")
        elif args.command == "kb" and args.kb_command == "list":
            for kb_id, name in list_knowledge_bases(args.db):
                print(f"{kb_id}\t{name}")
        elif args.command == "import":
            outcomes = import_directory(
                args.db,
                args.kb,
                args.dir,
                retain_original=args.originals == "copy",
            )
            for outcome in outcomes:
                if outcome.error:
                    print(f"FAILED\t{outcome.relative_path}\t{outcome.error}")
                else:
                    print(
                        f"{outcome.status.upper()}\t{outcome.relative_path}"
                        f"\tv{outcome.version_no}"
                    )
            failures = sum(outcome.status == "failed" for outcome in outcomes)
            print(f"Scanned {len(outcomes)} supported files; {failures} failed.")
            return 1 if failures else 0
        elif args.command == "docs" and args.docs_command == "list":
            for relative_path, version_no in list_documents(args.db, args.kb):
                print(f"{relative_path}\tv{version_no}")
        elif args.command == "chunks" and args.chunks_command == "list":
            for chunk in list_active_chunks(args.db, args.kb):
                print(
                    f"{chunk.relative_path}\tv{chunk.version_no}"
                    f"\tchunk {chunk.chunk_no}\tL{chunk.start_line}-L{chunk.end_line}"
                    f"\t{len(chunk.content)} chars\t{chunk.heading}"
                )
        elif args.command == "search":
            hits = search_knowledge_base(
                args.db, args.kb, args.query, limit=args.limit
            )
            for rank, hit in enumerate(hits, start=1):
                chunk = hit.chunk
                excerpt = " ".join(chunk.content.split())[:120]
                print(
                    f"{rank}. {chunk.relative_path} v{chunk.version_no} "
                    f"L{chunk.start_line}-L{chunk.end_line} "
                    f"score={hit.score:.4f}\n   {excerpt}"
                )
            if not hits:
                print("No matching source chunks found.")
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
