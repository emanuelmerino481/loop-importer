"""Candidate evaluator; metric definition is not frozen."""


def evaluate(checkpoint: str) -> dict[str, float]:
    raise NotImplementedError(f"Evaluation is intentionally disabled; checkpoint={checkpoint}")
