import csv
import json
from typing import List, Tuple

from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sentence_transformers import CrossEncoder, InputExample
from torch.utils.data import DataLoader

from my_player.helpers.constants import (
    SONGLINK_TRAIN_DATASET,
    RERANKER_MODEL,
    RERANKER_MODEL_DIR,
    RERANKER_EPOCHS,
    RERANKER_BATCH_SIZE,
    RERANKER_TEST_SPLIT,
    TRAINING_META_FILE,
    MIN_NEW_SAMPLES_FOR_RETRAIN,
    TRAINING_SEQUENCE_LENGTH
)
from my_player.models.training_sample import Sample


def _load_dataset() -> List[Sample]:
    if not SONGLINK_TRAIN_DATASET.exists():
        raise FileNotFoundError(f"Training dataset not found: {SONGLINK_TRAIN_DATASET}")

    samples: List[Sample] = []

    with SONGLINK_TRAIN_DATASET.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        needed = {"query", "title", "channel", "description", "duration", "label"}
        if not needed.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV missing required columns: {needed}")

        for row in reader:
            query = row["query"].strip()
            title = row["title"].strip()
            channel = row["channel"].strip()
            description = row["description"].strip()
            duration = row["duration"].strip()
            label = float(row["label"])

            if not query or not title:
                continue

            doc = (
                f"Title: {title}\n"
                f"Channel: {channel}\n"
                f"Description: {description}\n"
                f"Duration: {duration} seconds"
            )

            samples.append(Sample(query=query, doc=doc, label=label))

    return samples


def _pairs_and_labels(samples: List[Sample]) -> Tuple[List[Tuple[str, str]], List[float]]:
    pairs: List[Tuple[str, str]] = [(s.query, s.doc) for s in samples]
    labels: List[float] = [s.label for s in samples]
    return pairs, labels


def _to_input_examples(
    pairs: List[Tuple[str, str]],
    labels: List[float],
) -> List[InputExample]:
    return [
        InputExample(texts=[query, doc], label=float(label))
        for (query, doc), label in zip(pairs, labels)
    ]


def _load_last_trained_count() -> int | None:
    if not TRAINING_META_FILE.exists():
        return None

    try:
        with TRAINING_META_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        value = data.get("num_samples")
        return int(value) if value is not None else None
    except Exception:
        return None


def _save_last_trained_count(count: int) -> None:
    RERANKER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with TRAINING_META_FILE.open("w", encoding="utf-8") as f:
        json.dump({"num_samples": count}, f, ensure_ascii=False, indent=2)


def _should_train(current_count: int) -> bool:
    last_count = _load_last_trained_count()

    if last_count is None:
        print(
            f"[INFO] No previous training metadata found. "
            f"Training from scratch with {current_count} samples."
        )
        return True

    delta = current_count - last_count
    if delta < MIN_NEW_SAMPLES_FOR_RETRAIN:
        print(
            f"[INFO] Dataset grew by only {delta} samples "
            f"(last: {last_count}, current: {current_count})."
        )
        print(
            f"[INFO] Skipping training. Waiting for at least "
            f"{MIN_NEW_SAMPLES_FOR_RETRAIN} new samples."
        )
        return False

    print(
        f"[INFO] Dataset grew from {last_count} → {current_count} "
        f"(+{delta}). Triggering retrain."
    )
    return True


def train() -> None:
    print(f"[INFO] Loading dataset → {SONGLINK_TRAIN_DATASET}")
    samples = _load_dataset()
    current_count = len(samples)

    if not _should_train(current_count):
        print("[INFO] Auto-train condition not met. Exiting.")
        return

    # Stratify by binary label (>= 0.5 treated as positive)
    stratify_labels = [1 if s.label >= 0.5 else 0 for s in samples]

    train_samples, val_samples = train_test_split(
        samples,
        test_size=RERANKER_TEST_SPLIT,
        random_state=42,
        shuffle=True,
        stratify=stratify_labels,
    )

    train_pairs, train_labels = _pairs_and_labels(train_samples)
    val_pairs, val_labels = _pairs_and_labels(val_samples)

    print(f"[INFO] Training samples: {len(train_samples)}")
    print(f"[INFO] Validation samples: {len(val_samples)}")

    print(f"[INFO] Loading model base: {RERANKER_MODEL}")
    model = CrossEncoder(
        RERANKER_MODEL,
        num_labels=1,
        max_length=TRAINING_SEQUENCE_LENGTH,   # reduce sequence length (default is usually 512)
        device="cuda"     # force GPU explicitly
    )

    # Prepare DataLoader for the CrossEncoder.fit() API
    train_examples = _to_input_examples(train_pairs, train_labels)
    train_dataloader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=RERANKER_BATCH_SIZE,
    )

    total_steps = len(train_dataloader) * RERANKER_EPOCHS
    warmup_steps = max(1, int(0.1 * total_steps))

    print("[INFO] Starting training…")
    model.fit(
        train_dataloader=train_dataloader,
        epochs=RERANKER_EPOCHS,
        warmup_steps=warmup_steps,
        show_progress_bar=True,
    )

    # Validation evaluation
    print("[INFO] Evaluating…")
    preds = model.predict(val_pairs)

    try:
        auc = roc_auc_score(val_labels, preds)
        print(f"[INFO] Validation ROC-AUC = {auc:.4f}")
    except Exception:
        print("[WARN] Validation: ROC-AUC could not be computed")

    print(f"[INFO] Saving finetuned model → {RERANKER_MODEL_DIR}")
    RERANKER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save(str(RERANKER_MODEL_DIR))

    _save_last_trained_count(current_count)

    print("[INFO] Training complete")


if __name__ == "__main__":
    train()
