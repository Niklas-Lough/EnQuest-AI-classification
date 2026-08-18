import json
import logging
import asyncio
import re

from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential

from enquest_prompt import hazard_labels, human_factors_labels

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class EnquestClassifierClient:
    """Calls a pre-provisioned Azure AI Foundry Agent (created and
    configured via the Foundry portal -- see enquest_config.py and
    enquest_agent_setup.py) via the OpenAI Responses API to assign one
    Hazard label and one Human Factors label per observation, per the
    BBSS AI Classification Taxonomy.

    Important: this project's agent endpoint rejects `instructions` and
    `text` (response_format) on the request -- "Not allowed when agent is
    specified" -- so classification behaviour is controlled entirely by
    the agent's portal-configured Instructions field (built from
    enquest_taxonomy.json via enquest_prompt.build_agent_instructions and
    pasted in manually; see enquest_agent_setup.py). Only the observation
    text is sent per call. Whenever the taxonomy changes, re-print the
    instructions and re-paste them into the portal.

    Uses AIProjectClient.get_openai_client(agent_name=...), which returns
    an OpenAI-SDK-compatible AsyncOpenAI client pointed at the agent's own
    endpoint. Does NOT use azure-ai-agents' classic threads/messages/runs
    surface -- that surface returned 405 against this project's agent type.

    Use as an async context manager so the underlying credential and
    client are opened/closed once per run, not once per card:

        async with EnquestClassifierClient(...) as classifier:
            result = await classifier.classify(text, row_id)
    """

    def __init__(self, project_endpoint, agent_name, taxonomy, model=None, max_retries=3, retry_delay=2):
        self.project_endpoint = project_endpoint
        self.agent_name = agent_name
        self.model = model
        self.hazard_labels = hazard_labels(taxonomy)
        self.human_factors_labels = human_factors_labels(taxonomy)
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self._credential = None
        self._project_client = None
        self._openai_client = None

    async def __aenter__(self):
        self._credential = DefaultAzureCredential()
        await self._credential.__aenter__()
        self._project_client = AIProjectClient(
            endpoint=self.project_endpoint,
            credential=self._credential,
            allow_preview=True,
        )
        await self._project_client.__aenter__()
        self._openai_client = self._project_client.get_openai_client(agent_name=self.agent_name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._openai_client is not None:
            await self._openai_client.close()
        if self._project_client is not None:
            await self._project_client.__aexit__(exc_type, exc_val, exc_tb)
        if self._credential is not None:
            await self._credential.__aexit__(exc_type, exc_val, exc_tb)

    def _parse_response(self, content, row_id):
        cleaned = _CODE_FENCE_RE.sub("", content.strip()).strip()
        try:
            data = json.loads(cleaned)
            hazard = data["hazard"]
            human_factors = data["human_factors"]

            if hazard["label"] not in self.hazard_labels:
                logging.warning(f"RowId {row_id}: unrecognised hazard label '{hazard['label']}'")
                return None
            if human_factors["label"] not in self.human_factors_labels:
                logging.warning(f"RowId {row_id}: unrecognised human factors label '{human_factors['label']}'")
                return None
            if hazard["confidence"] not in ("High", "Medium", "Low"):
                hazard["confidence"] = "Low"
            if human_factors["confidence"] not in ("High", "Medium", "Low"):
                human_factors["confidence"] = "Low"

            return {
                "hazard_label": hazard["label"],
                "hazard_confidence": hazard["confidence"],
                "human_factors_label": human_factors["label"],
                "human_factors_confidence": human_factors["confidence"],
            }
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logging.warning(f"RowId {row_id}: failed to parse classification response: {e}. Raw content: {content[:500]}")
            return None

    async def classify(self, observation_text, row_id):
        """Classifies a single observation's concatenated text on both
        dimensions via the Foundry agent's Responses API endpoint. Retries
        up to `self.max_retries` times on failure (API error, timeout,
        malformed response). Returns a dict (see _parse_response) or None
        if all attempts failed.
        """
        request_kwargs = {
            "input": f'Observation text: "{observation_text}"',
        }
        if self.model:
            request_kwargs["model"] = self.model

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._openai_client.responses.create(**request_kwargs)
                content = response.output_text
                if content:
                    parsed = self._parse_response(content, row_id)
                    if parsed is not None:
                        return parsed
                else:
                    logging.warning(f"RowId {row_id}: empty response text, attempt {attempt}")
            except Exception as e:
                logging.warning(f"Exception during classification for RowId {row_id}, attempt {attempt}: {str(e)}")

            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay)

        logging.error(f"Failed to classify RowId {row_id} after {self.max_retries} attempts")
        return None
