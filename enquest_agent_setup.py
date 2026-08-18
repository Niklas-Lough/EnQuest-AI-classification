"""Helper for the EnQuest BBSS Foundry Agent.

IMPORTANT: for this project's Agent type (the modern Foundry Agent Service,
reached via the OpenAI Responses API), there is currently no programmatic
create/update path in azure-ai-projects -- Agents are created and configured
through the Foundry portal itself. You create the Agent there (give it a
name, e.g. "EnQuestObservationClassifier", and pick the model deployment
to bind it to), then set ENQUEST_BBSS_FOUNDRY_AGENT_NAME to that name.

The agent's endpoint also rejects `instructions` and `text` (response
format) overrides per API call ("Not allowed when agent is specified"), so
classification behaviour is controlled ENTIRELY by whatever is pasted into
the agent's "Instructions" field in the portal. This script does NOT create
or modify the agent. It does two things:

1. REQUIRED, once and after every taxonomy change: prints the full
   instructions text (built from enquest_taxonomy.json) for you to copy
   and paste into the portal's Agent > Instructions field.
2. Optional: a lightweight connectivity check -- sends one real
   classification call for a trivial observation and confirms a
   well-formed response comes back, so you can catch endpoint/auth/agent-
   name/instructions problems before running the full local test or backfill.

Usage:
    python enquest_agent_setup.py              # print instructions to paste into the portal
    python enquest_agent_setup.py --check       # also do the connectivity check
"""
import argparse
import asyncio
import json

import enquest_config as config
from enquest_prompt import load_taxonomy, build_agent_instructions, build_response_json_schema
from enquest_classifier_client import EnquestClassifierClient


def parse_args():
    parser = argparse.ArgumentParser(description="Print EnQuest BBSS Foundry agent instructions to paste into the portal, optionally verify connectivity.")
    parser.add_argument("--check", action="store_true", help="Also send one real classification call to verify the agent is reachable and correctly configured.")
    return parser.parse_args()


async def run_check(taxonomy):
    print("\nRunning connectivity check against the live agent...")
    async with EnquestClassifierClient(
        config.get_foundry_project_endpoint(),
        config.get_foundry_agent_name(),
        taxonomy,
        model=config.get_foundry_model_deployment(),
        max_retries=1,
    ) as classifier:
        result = await classifier.classify("Great teamwork. Congratulated team.", row_id="connectivity-check")

    if result is None:
        print("FAILED -- see log output above / enquest_classification.log for details.")
        print("If the failure mentions JSON parsing, the agent's Instructions field likely")
        print("doesn't have the taxonomy prompt pasted in yet -- copy the text printed above.")
    else:
        print("OK -- agent responded with a well-formed classification:")
        print(json.dumps(result, indent=2))


def main():
    args = parse_args()

    taxonomy = load_taxonomy()
    instructions = build_agent_instructions(taxonomy)
    response_json_schema = build_response_json_schema(taxonomy)

    print("=" * 100)
    print("PASTE THIS INTO THE FOUNDRY PORTAL -> your agent -> Instructions field:")
    print("=" * 100)
    print(instructions)
    print("=" * 100)
    print("Reference only (NOT sent over the API for this agent type -- structured-output")
    print("enforcement isn't available per-call once an agent is specified; the OUTPUT FORMAT")
    print("section above is what actually constrains the response shape):")
    print("=" * 100)
    print(json.dumps(response_json_schema, indent=2))

    if args.check:
        asyncio.run(run_check(taxonomy))


if __name__ == "__main__":
    main()
