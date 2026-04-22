import os
import logging
import asyncio
from datetime import datetime
from ClassifierClient import ClassifierClient
from sql_engine import SQLEngine
from process_batch import process_batch
import aiohttp

async def main():
    logging.basicConfig(filename="classification.log", level=logging.INFO)
    start_time = datetime.now()

    # Configuration
    spa_db_connection = os.environ.get("SPA_DEMOIND_PROD_CONNECTION")
    spa_db_connection_api_key = os.environ.get("SPA_DEMOIND_AZURE_OPENAI_API_KEY")
    spa_db_connection_endpoint = "https://oai-euw-prd-spa-demoind-fg.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2025-01-01-preview"

    sql_engine = SQLEngine(spa_db_connection)
    classifier = ClassifierClient(spa_db_connection_api_key, spa_db_connection_endpoint)

    # Prepare staging table (drops and recreates)
    sql_engine.prepare_staging_table()

    # Fetch all observations to classify
    observations = sql_engine.get_pending_observations()

    batch_size = 500
    semaphore = asyncio.Semaphore(3)

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(observations), batch_size):
            batch = observations[i:i + batch_size]
        
            print(f"Processing batch {i // batch_size + 1}")
            await process_batch(batch, classifier, sql_engine, session, semaphore)
            # staging updates and inserts happen in process_batch / SQL engine now

    print(f"Execution time: {datetime.now() - start_time}")

if __name__ == "__main__":
    asyncio.run(main())
