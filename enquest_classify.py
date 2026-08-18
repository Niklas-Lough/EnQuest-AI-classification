import logging
import asyncio
from datetime import datetime

import enquest_config as config
from enquest_sql_engine import EnquestSQLEngine
from enquest_classifier_client import EnquestClassifierClient
from enquest_process_batch import process_batch
from enquest_prompt import load_taxonomy


async def classify_observations(force=False, limit=1_000_000, concurrency=None):
    """Shared classification entry point used by both the on-demand backfill
    script and the daily webjob.

    force=False (default): only classifies cards where AI_Hazard_Category
    and AI_Human_Factors_Category are both still NULL -- safe to re-trigger
    without reprocessing already-classified cards.

    force=True: reclassifies every card regardless of current field state.
    Use this after a taxonomy revision (new label, retuned keywords,
    changed precedence rules) -- but note the agent's portal-configured
    Instructions field must also be updated to match (re-run
    enquest_agent_setup.py to print the new text and paste it in), since
    that's the only place classification behaviour lives for this agent type.

    concurrency: overrides config.CONCURRENCY for this run only (e.g. a
    larger value for a one-off backfill vs. the daily webjob's steady-state
    default). None uses config.CONCURRENCY.
    """
    run_start = datetime.now()
    logging.info(f"EnQuest classification run started. force={force}")

    sql_engine = EnquestSQLEngine(config.get_db_connection_string())
    sql_engine.ensure_schema()

    taxonomy = load_taxonomy()

    observations = sql_engine.get_pending_observations(limit=limit, force=force)
    total = len(observations)
    logging.info(f"Fetched {total} observation(s) to classify (force={force}).")

    classified_count = 0
    failed_count = 0
    confidence_retried = 0
    confidence_resolved = 0
    confidence_exhausted = 0
    semaphore = asyncio.Semaphore(concurrency or config.CONCURRENCY)

    async with EnquestClassifierClient(
        config.get_foundry_project_endpoint(),
        config.get_foundry_agent_name(),
        taxonomy,
        model=config.get_foundry_model_deployment(),
        max_retries=config.MAX_RETRIES,
        retry_delay=config.RETRY_DELAY_SECONDS,
    ) as classifier:
        for i in range(0, total, config.BATCH_SIZE):
            batch = observations[i:i + config.BATCH_SIZE]
            batch_num = i // config.BATCH_SIZE + 1
            print(f"Processing batch {batch_num} ({len(batch)} cards)")
            ok, failed, stats = await process_batch(batch, classifier, sql_engine, semaphore)
            classified_count += ok
            failed_count += failed
            confidence_retried += stats["confidence_retried"]
            confidence_resolved += stats["confidence_resolved"]
            confidence_exhausted += stats["confidence_exhausted"]

    duration = datetime.now() - run_start
    logging.info(
        f"EnQuest classification run finished. "
        f"force={force} total_fetched={total} classified={classified_count} "
        f"failed={failed_count} confidence_retried={confidence_retried} "
        f"confidence_resolved={confidence_resolved} confidence_exhausted={confidence_exhausted} "
        f"duration={duration}"
    )
    print(
        f"EnQuest classification run complete. "
        f"Fetched={total} Classified={classified_count} Failed={failed_count} "
        f"ConfidenceRetried={confidence_retried} ConfidenceResolved={confidence_resolved} "
        f"ConfidenceExhausted={confidence_exhausted} Duration={duration}"
    )

    return {
        "total_fetched": total,
        "classified": classified_count,
        "failed": failed_count,
        "confidence_retried": confidence_retried,
        "confidence_resolved": confidence_resolved,
        "confidence_exhausted": confidence_exhausted,
        "duration_seconds": duration.total_seconds(),
    }
