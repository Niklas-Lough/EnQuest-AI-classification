import asyncio
import logging

async def process_batch(observations, classifier, sql_engine, session, semaphore):
    update_buffer = []

    async def classify_and_store(obs):
        async with semaphore:
            try:
                classification, justification = await classifier.classify(session, obs)
                # Append to buffer instead of updating DB immediately
                update_buffer.append({
                    "RowId": obs["RowId"],
                    "Classification": classification,
                    "Justification": justification
                })
            except Exception as e:
                logging.error(f"Failed RowId {obs['RowId']}: {e}")

    tasks = [classify_and_store(obs) for obs in observations]
    await asyncio.gather(*tasks)

    # Bulk update after batch finishes
    if update_buffer:
        sql_engine.update_classification_batch(update_buffer)

