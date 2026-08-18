"""Local, DB-free smoke test for the EnQuest BBSS Foundry classification
agent. Reads real sample rows from test_fixtures/sample_observations.csv,
sends each through the live agent, and prints the results for manual
verification against the taxonomy in enquest_taxonomy.json -- it never
touches dbo.FormData_Master or the review log table.

Usage:
    python enquest_local_test.py                  # first 15 rows
    python enquest_local_test.py --n 5             # first 5 rows
    python enquest_local_test.py --rowid 32792      # a single specific row

Requires ENQUEST_BBSS_FOUNDRY_PROJECT_ENDPOINT (the bare project endpoint)
and ENQUEST_BBSS_FOUNDRY_AGENT_NAME (the Agent's name as configured in the
Foundry portal) to be set. ENQUEST_BBSS_FOUNDRY_MODEL_DEPLOYMENT is optional.
No DB connection string is needed for this script.

Also requires the agent's Instructions field (in the Foundry portal) to
already contain the taxonomy prompt -- run enquest_agent_setup.py to print
it if you haven't pasted it in yet. This script only sends observation
text per call; the agent type here rejects per-call instructions overrides.
"""
import argparse
import asyncio
import csv
import textwrap

import enquest_config as config
from enquest_classifier_client import EnquestClassifierClient
from enquest_prompt import load_taxonomy, build_observation_text

DEFAULT_CSV = "test_fixtures/sample_observations.csv"


def parse_args():
    parser = argparse.ArgumentParser(description="Run real EnQuest sample rows through the live Foundry agent for manual verification.")
    parser.add_argument("--csv", default=DEFAULT_CSV, help=f"Path to the sample CSV (default: {DEFAULT_CSV})")
    parser.add_argument("--n", type=int, default=15, help="Number of rows to classify (default: 15)")
    parser.add_argument("--rowid", type=int, default=None, help="Classify only this specific RowId")
    return parser.parse_args()


def load_rows(csv_path, n, only_row_id):
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_id = int(row["RowId"])
            if only_row_id is not None and row_id != only_row_id:
                continue
            rows.append({
                "RowId": row_id,
                "Hazard_Description": row.get("Hazard_Description", ""),
                "Action_Taken": row.get("Action_Taken", ""),
            })
            if only_row_id is None and len(rows) >= n:
                break
    return rows


def _wrap(text, width=100):
    return "\n      ".join(textwrap.wrap(text, width=width)) or "(empty)"


async def main():
    args = parse_args()
    rows = load_rows(args.csv, args.n, args.rowid)

    if not rows:
        print("No rows loaded -- check --csv / --rowid.")
        return

    print(f"Loaded {len(rows)} row(s) from {args.csv}\n")

    taxonomy = load_taxonomy()
    semaphore = asyncio.Semaphore(config.CONCURRENCY)

    async with EnquestClassifierClient(
        config.get_foundry_project_endpoint(),
        config.get_foundry_agent_name(),
        taxonomy,
        model=config.get_foundry_model_deployment(),
        max_retries=config.MAX_RETRIES,
        retry_delay=config.RETRY_DELAY_SECONDS,
    ) as classifier:

        async def run_one(row):
            async with semaphore:
                text = build_observation_text(row["Hazard_Description"], row["Action_Taken"])
                result = await classifier.classify(text, row["RowId"])
                return row, text, result

        results = await asyncio.gather(*(run_one(r) for r in rows))

    for row, text, result in results:
        print("=" * 100)
        print(f"RowId {row['RowId']}")
        print(f"  Text: {_wrap(text)}")
        if result is None:
            print("  ** CLASSIFICATION FAILED (see enquest_classification.log / stderr) **")
            continue
        print(f"  Hazard:         {result['hazard_label']}  [{result['hazard_confidence']}]")
        print(f"  Human Factors:  {result['human_factors_label']}  [{result['human_factors_confidence']}]")

    print("=" * 100)
    failed = sum(1 for _, _, r in results if r is None)
    print(f"\n{len(results) - failed}/{len(results)} classified. Compare each against enquest_taxonomy.json's precedence rules.")


if __name__ == "__main__":
    asyncio.run(main())
