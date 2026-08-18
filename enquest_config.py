import os

try:
    from dotenv import load_dotenv
    load_dotenv()  # convenience for local dev/testing; no-op in the webjob environment
except ImportError:
    pass

# Per-customer settings for the EnQuest BBSS Hazard / Human Factors classification.
# Mirrors the env-var-driven style already used for the other customer in main.py,
# kept separate so neither customer's config can be accidentally cross-wired.

DB_CONNECTION_ENV = "ENQUEST_BBSS_PROD_CONNECTION"

# Azure AI Foundry project + Agent used for classification. This targets the
# modern Foundry Agent Service (OpenAI Responses API), reached via
# AIProjectClient.get_openai_client(agent_name=...) -- NOT the classic
# Assistants/threads/runs surface (azure-ai-agents), which this project's
# agent type does not support (confirmed: /assistants returns 405).
#
# FOUNDRY_PROJECT_ENDPOINT is the *bare* project endpoint, e.g.:
#   https://<resource>.services.ai.azure.com/api/projects/<project-name>
# -- NOT the full agent-specific endpoint the Foundry portal shows you
# (which looks like ".../agents/<agent-name>/endpoint/protocols/openai/responses").
# The SDK builds that longer URL itself from the project endpoint + agent name.
FOUNDRY_PROJECT_ENDPOINT_ENV = "ENQUEST_BBSS_FOUNDRY_PROJECT_ENDPOINT"

# The Agent's name as configured in the Foundry portal (e.g. "EnQuestObservationClassifier").
# The agent must already exist in the portal -- there is currently no
# programmatic create/update path for this agent type in azure-ai-projects.
FOUNDRY_AGENT_NAME_ENV = "ENQUEST_BBSS_FOUNDRY_AGENT_NAME"

# Optional. The underlying model deployment name (e.g. "gpt-5-mini"). Since
# the endpoint is already scoped to a specific agent, this can usually be
# left unset -- the agent's own bound model applies, and the SDK omits the
# field entirely from the request when this is None.
FOUNDRY_MODEL_DEPLOYMENT_ENV = "ENQUEST_BBSS_FOUNDRY_MODEL_DEPLOYMENT"

TABLE_NAME = "dbo.FormData_Master"
REVIEW_LOG_TABLE_NAME = "dbo.AI_Classification_Review_Log"

HAZARD_FIELD = "AI_Hazard_Category"
HUMAN_FACTORS_FIELD = "AI_Human_Factors_Category"

TAXONOMY_FILE = os.path.join(os.path.dirname(__file__), "enquest_taxonomy.json")

BATCH_SIZE = 500
CONCURRENCY = 3
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

# Separate from MAX_RETRIES above (which covers transport/parse failures
# inside EnquestClassifierClient.classify). This is a business-logic retry:
# if either dimension comes back Low confidence, re-run the whole card
# (both dimensions are produced together in one call, so a retry
# regenerates both) up to this many extra times, hoping for a more
# confident result. Bounded, not retry-until-confident -- there's no
# guarantee of convergence (e.g. if the deployment uses low-temperature/
# near-deterministic decoding, retries may just reproduce the same
# result). Whatever confidence remains after the budget is exhausted gets
# persisted anyway and flagged in the review log -- a card that's still
# Low after repeated independent attempts is a genuinely meaningful
# "the model is unsure" signal, not something to keep retrying forever.
MAX_CONFIDENCE_RETRIES = 2

LOG_FILE = "enquest_classification.log"


def get_db_connection_string():
    value = os.environ.get(DB_CONNECTION_ENV)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {DB_CONNECTION_ENV}")
    return value


def get_foundry_project_endpoint():
    value = os.environ.get(FOUNDRY_PROJECT_ENDPOINT_ENV)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {FOUNDRY_PROJECT_ENDPOINT_ENV}")
    return value


def get_foundry_agent_name():
    value = os.environ.get(FOUNDRY_AGENT_NAME_ENV)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {FOUNDRY_AGENT_NAME_ENV}")
    return value


def get_foundry_model_deployment():
    """Optional. Returns None if unset (the agent's own bound model applies)."""
    return os.environ.get(FOUNDRY_MODEL_DEPLOYMENT_ENV) or None
