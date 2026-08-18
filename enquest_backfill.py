import argparse
import logging
import asyncio

import enquest_config as config
from enquest_classify import classify_observations

# On-demand / backfill entry point for an EnQuest team member to trigger
# manually, e.g. right after this feature ships to classify the full
# historical dataset, or after a taxonomy revision with --force.
#
# Usage:
#   python enquest_backfill.py                     # classify only unclassified cards
#   python enquest_backfill.py --force              # reclassify every card
#   python enquest_backfill.py --limit 5000         # cap how many cards this run processes
#   python enquest_backfill.py --concurrency 10     # raise parallel agent calls for this run


def parse_args():
    parser = argparse.ArgumentParser(description="EnQuest BBSS Hazard / Human Factors classification backfill.")
    parser.add_argument("--force", action="store_true", help="Reclassify every card, even if already labelled.")
    parser.add_argument("--limit", type=int, default=1_000_000, help="Maximum number of cards to process this run.")
    parser.add_argument("--concurrency", type=int, default=None, help=f"Parallel agent calls for this run only (default: config.CONCURRENCY = {config.CONCURRENCY}).")
    return parser.parse_args()


async def main():
    logging.basicConfig(filename=config.LOG_FILE, level=logging.INFO)
    args = parse_args()
    await classify_observations(force=args.force, limit=args.limit, concurrency=args.concurrency)


if __name__ == "__main__":
    asyncio.run(main())
