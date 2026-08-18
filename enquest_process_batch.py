import asyncio
import logging

import enquest_config as config
from enquest_prompt import build_observation_text


def _is_low(result):
    return result["hazard_confidence"] == "Low" or result["human_factors_confidence"] == "Low"


async def process_batch(observations, classifier, sql_engine, semaphore):
    """Classifies one batch of observations on both dimensions and writes
    results. A per-card AI failure (timeout, malformed response) is logged
    and that card is simply left unclassified for the next run to retry --
    it never aborts the batch.

    If either dimension comes back Low confidence, the whole card (both
    dimensions are produced together in one call) is re-classified up to
    config.MAX_CONFIDENCE_RETRIES extra times, hoping for a more confident
    result. Whatever confidence remains after that budget is exhausted is
    persisted anyway -- a card is never left unclassified purely because
    of confidence -- and still-Low dimensions go to the review log, same
    as before.
    """
    update_buffer = []
    review_log_buffer = []
    stats = {"confidence_retried": 0, "confidence_resolved": 0, "confidence_exhausted": 0}

    async def classify_and_store(obs):
        async with semaphore:
            try:
                text = build_observation_text(obs["Hazard_Description"], obs["Action_Taken"])
                row_id = obs["RowId"]

                max_attempts = 1 + config.MAX_CONFIDENCE_RETRIES
                result = None
                for attempt in range(1, max_attempts + 1):
                    result = await classifier.classify(text, row_id)
                    if result is None:
                        return  # already logged inside classifier; leave both fields NULL for retry

                    if not _is_low(result):
                        if attempt > 1:
                            stats["confidence_resolved"] += 1
                        break

                    if attempt == 1:
                        stats["confidence_retried"] += 1
                    if attempt < max_attempts:
                        logging.info(f"RowId {row_id}: Low confidence on attempt {attempt}/{max_attempts}, retrying")
                    else:
                        stats["confidence_exhausted"] += 1
                        logging.warning(f"RowId {row_id}: still Low confidence after {max_attempts} attempts, keeping best result and flagging for review")

                update_buffer.append({
                    "RowId": row_id,
                    "HazardLabel": result["hazard_label"],
                    "HumanFactorsLabel": result["human_factors_label"],
                })

                if result["hazard_confidence"] == "Low":
                    review_log_buffer.append({
                        "RowId": row_id,
                        "Dimension": "Hazard",
                        "Label": result["hazard_label"],
                        "Confidence": result["hazard_confidence"],
                    })
                if result["human_factors_confidence"] == "Low":
                    review_log_buffer.append({
                        "RowId": row_id,
                        "Dimension": "Human Factors",
                        "Label": result["human_factors_label"],
                        "Confidence": result["human_factors_confidence"],
                    })
            except Exception as e:
                logging.error(f"Failed RowId {obs['RowId']}: {e}")

    tasks = [classify_and_store(obs) for obs in observations]
    await asyncio.gather(*tasks)

    if update_buffer:
        sql_engine.update_classification_batch(update_buffer)
    if review_log_buffer:
        sql_engine.insert_review_log_batch(review_log_buffer)

    classified = len(update_buffer)
    failed = len(observations) - classified
    return classified, failed, stats
