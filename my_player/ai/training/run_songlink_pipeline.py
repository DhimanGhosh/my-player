"""
Run the full SongLink training pipeline with a single command.

Steps:
1) Build raw dataset from queries.txt       → build_songlink_dataset.py
2) Prepare cleaned/labelled train CSV       → prepare_songlink_train.py
3) Train / fine-tune reranker model         → train_songlink_reranker.py

Usage (from project root):

    python -m my_player.ai.training.run_songlink_pipeline

Optional flags:

    python -m my_player.ai.training.run_songlink_pipeline \
        --skip-build \
        --skip-prepare \
        --skip-train

This script uses `runpy.run_module` so it does not depend on the
internal function names of the individual step scripts.
"""
import argparse
import runpy
import sys
from pathlib import Path


def _run_module(module_name: str) -> None:
    """Run a module as if called with `python -m module_name`."""
    print(f"[PIPELINE] Running step → {module_name}")
    runpy.run_module(module_name, run_name="__main__")
    print(f"[PIPELINE] Finished step → {module_name}\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full SongLink reranker pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building raw dataset from queries.txt",
    )
    parser.add_argument(
        "--skip-prepare",
        action="store_true",
        help="Skip preparing the cleaned training dataset",
    )
    parser.add_argument(
        "--skip-train",
        action="store_true",
        help="Skip training the reranker model",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # Optional: basic sanity check that we're in a project with my_player
    project_root = Path(__file__).resolve().parents[3]
    print(f"[PIPELINE] Project root detected as: {project_root}")

    if not args.skip_build:
        _run_module("my_player.ai.training.build_songlink_dataset")
    else:
        print("[PIPELINE] Skipping build step (raw dataset from queries.txt)\n")

    if not args.skip_prepare:
        _run_module("my_player.ai.training.prepare_songlink_train")
    else:
        print("[PIPELINE] Skipping prepare step (clean training CSV)\n")

    if not args.skip_train:
        _run_module("my_player.ai.training.train_songlink_reranker")
    else:
        print("[PIPELINE] Skipping train step (reranker fine-tuning)\n")

    print("[PIPELINE] All requested steps completed.")


if __name__ == "__main__":
    main(sys.argv[1:])
