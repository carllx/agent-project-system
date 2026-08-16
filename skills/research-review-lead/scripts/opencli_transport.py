#!/usr/bin/env python3
"""Thin CLI facade for the Minimal Browser Review Bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .minimal_bridge import bootstrap_conversation, dispatch_review, reconcile_review
except ImportError:
    from minimal_bridge import bootstrap_conversation, dispatch_review, reconcile_review


def review_bootstrap_command(args: argparse.Namespace) -> int:
    """Create an inert Review conversation via OpenCLI --new."""
    try:
        res = bootstrap_conversation(
            timeout_seconds=args.timeout,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, ValueError, TimeoutError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


def review_command(args: argparse.Namespace) -> int:
    """Minimal Browser Review Bridge dispatch and reconcile."""
    if getattr(args, "reconcile", False):
        if not args.conversation:
            print(json.dumps({"error": "--conversation is required for --reconcile"}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        try:
            res = reconcile_review(
                request_id=args.request_id,
                artifact_id=args.artifact_id,
                conversation_id=args.conversation,
                timeout_seconds=args.timeout,
            )
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0 if res.get("status") in {"RESPONSE_READY", "RESPONSE_PENDING"} else 1
        except (RuntimeError, ValueError, TimeoutError) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1

    if not getattr(args, "conversation", None):
        print(json.dumps({"error": "--conversation is required for formal review. Use review-bootstrap to create one first."}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    prompt_text = ""
    if getattr(args, "prompt_file", None):
        with open(args.prompt_file, "r", encoding="utf-8") as stream:
            prompt_text = stream.read()
    elif getattr(args, "prompt", None):
        prompt_text = args.prompt
    else:
        print(json.dumps({"error": "Either --prompt or --prompt-file is required"}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    try:
        res = dispatch_review(
            request_id=args.request_id,
            artifact_id=args.artifact_id,
            review_prompt=prompt_text,
            conversation_id=args.conversation,
            timeout_seconds=args.timeout,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("status") in {"RESPONSE_READY", "CACHED_RESPONSE_READY", "RESPONSE_PENDING"} else 1
    except (RuntimeError, ValueError, TimeoutError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    rev_boot = sub.add_parser("review-bootstrap", help="Create an inert Review conversation via OpenCLI --new")
    rev_boot.add_argument("--timeout", type=int, default=30)
    rev_boot.set_defaults(handler=review_bootstrap_command)

    rev = sub.add_parser("review", help="Minimal Browser Review Bridge dispatch and reconcile")
    rev.add_argument("--request-id", required=True, help="Unique review request identifier")
    rev.add_argument("--artifact-id", required=True, help="Artifact content SHA256")
    rev.add_argument("--prompt", help="Review task instructions")
    rev.add_argument("--prompt-file", help="File containing review task instructions")
    rev.add_argument("--conversation", required=True, help="Target established conversation ID")
    rev.add_argument("--timeout", type=int, default=30)
    rev.add_argument("--reconcile", action="store_true", help="Perform read-only reconciliation")
    rev.set_defaults(handler=review_command)

    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser().print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
