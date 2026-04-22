import asyncio
import aiohttp
import logging
import os
from datetime import datetime

class DataProcessor:
    def __init__(self, engine):
        self.engine = engine
        self.api_key = os.environ.get("SPA_DEMOIND_AZURE_OPENAI_API_KEY")
        self.endpoint = os.environ.get("SPA_DEMOIND_AZURE_OPENAI_ENDPOINT")

        logging.basicConfig(filename="classification_progress.log", level=logging.INFO,
                            format="%(asctime)s - %(message)s")

    def create_staging_table(self):
        query = """
        IF OBJECT_ID('dbo.APP_F_SPA_FormData_Master_Staging', 'U') IS NOT NULL
            DROP TABLE dbo.APP_F_SPA_FormData_Master_Staging;

        SELECT 
            *, 
            CAST(NULL AS NVARCHAR(255)) AS Classification,
            CAST(NULL AS NVARCHAR(MAX)) AS Justification
        INTO dbo.APP_F_SPA_FormData_Master_Staging
        FROM dbo.FormData_Master
        WHERE Submission_Date >= DATEADD(DAY, -300, CAST(GETDATE() AS DATE)) AND Facility = 'Aberdeen Facility 4';
        """
        self.engine.execute(query)

    def fetch_observations(self):
        query = """
        SELECT TOP(60000) RowId, iHazard_Description 
        FROM APP_F_SPA_FormData_Master_Staging 
        WHERE Classification IS NULL
        """
        rows = self.engine.fetchall(query)
        return [{"RowId": row[0], "iHazard_Description": row[1]} for row in rows]

    async def classify_observation(self, session, observation, semaphore, update_buffer):
        prompt = f"""
Classify the following safety observation into one of the predefined categories below, and provide a concise justification.

Categories:
Task Design, Work Environment, Communication, Human Error, Equipment and Tools, Behavioral Factors, 
Training and Competence, Leadership and Supervision, Organizational Processes, External Factors.

Safety Observation: "{observation['iHazard_Description']}"

Response Format:
Classification: [Selected Category]
Justification: [Brief explanation]
"""
        payload = {
            "messages": [
                {"role": "system", "content": "You classify safety observations..."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 255
        }

        headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }

        async with semaphore:
            try:
                async with session.post(self.endpoint, json=payload, headers=headers) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        content = response_data["choices"][0]["message"]["content"]
                        parts = content.split("Justification:", 1)
                        classification = parts[0].replace("Classification:", "").strip()
                        justification = parts[1].strip() if len(parts) > 1 else "No justification provided."

                        # Append to buffer
                        update_buffer.append({
                            "RowId": observation["RowId"],
                            "Classification": classification,
                            "Justification": justification
                        })
                    else:
                        logging.error(f"API error {response.status} for RowId {observation['RowId']}")
            except Exception as e:
                logging.error(f"Exception for RowId {observation['RowId']}: {str(e)}")

    async def process_all(self, observations):
        batch_size = 500
        semaphore = asyncio.Semaphore(3)

        async with aiohttp.ClientSession() as session:
            for i in range(0, len(observations), batch_size):
                batch = observations[i:i + batch_size]
                print(f"Processing batch {i // batch_size + 1}")

                update_buffer = []
                tasks = [self.classify_observation(session, obs, semaphore, update_buffer)
                         for obs in batch]
                await asyncio.gather(*tasks)

                if update_buffer:
                    # 1️⃣ Update staging table immediately
                    self.engine.update_classification_batch(update_buffer)

                    # 2️⃣ Insert classified rows into final table
                    row_ids = [r["RowId"] for r in update_buffer]
                    self.engine.insert_classified_data_rows(row_ids)

                    print(f"Inserted {len(row_ids)} rows into classification_test")

    def classify_observations(self):
        observations = self.fetch_observations()
        if observations:
            asyncio.run(self.process_all(observations))
        else:
            print("No observations to classify.")
