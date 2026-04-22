import pandas as pd
from datetime import datetime
import logging
import asyncio

class ClassifierClient:
    def __init__(self, spa_db_connection_api_key, spa_db_connection_endpoint, max_retries=3, retry_delay=2):
        self.api_key = spa_db_connection_api_key
        self.endpoint = spa_db_connection_endpoint
        self.headers = {
            "Content-Type": "application/json",
            "api-key": self.api_key
        }
        self.max_retries = max_retries
        self.retry_delay = retry_delay  # seconds between retries

        self.prompt_system = """
You are an intelligent assistant trained to analyze safety observation data and categorize it into predefined categories based on relevance and context. Your task is to determine the most appropriate category for each observation or indicate 'No category applicable' if none of the predefined categories apply.

Rules for Responses:
- Classification: the category name (e.g., Communication) or 'No category applicable'
- Justification: a concise explanation of why this category was selected, referencing specific details from the observation.
        """

        self.prompt_user_template = """Classify the following safety observation into one of the predefined categories below, and provide a concise justification for the classification.

Categories:
Task Design, Work Environment, Communication, Human Error, Equipment and Tools, Behavioral Factors,
Training and Competence, Leadership and Supervision, Organizational Processes, External Factors.

Safety Observation: {observation}

Response Format:
Classification: [Selected Category]
Justification: [Brief explanation]
"""

    async def classify(self, session, observation):
        """
        Classifies a single observation using the Azure OpenAI endpoint.
        Retries up to `self.max_retries` times on failure.
        Returns (classification, justification) or (None, None) if failed.
        """
        # Fill the observation text into the template
        user_content = self.prompt_user_template.format(observation=observation["iHazard_Description"])

        payload = {
            "messages": [
                {"role": "system", "content": self.prompt_system},
                {"role": "user", "content": user_content}
            ],
            "max_tokens": 255
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                async with session.post(self.endpoint, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        text = result["choices"][0]["message"]["content"].strip()

                        parts = text.split("Justification:", 1)
                        classification = parts[0].replace("Classification:", "").strip()
                        justification = parts[1].strip() if len(parts) > 1 else "No justification provided."

                        return classification, justification
                    else:
                        error_text = await response.text()
                        logging.warning(f"API Error {response.status}: {error_text} for RowId {observation.get('RowId')}, attempt {attempt}")
            except Exception as e:
                logging.warning(f"Exception during classification for RowId {observation.get('RowId')}, attempt {attempt}: {str(e)}")

            # Wait before retrying
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay)

        # If all attempts failed
        logging.error(f"Failed to classify RowId {observation.get('RowId')} after {self.max_retries} attempts")
        return None, None