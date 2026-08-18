import logging
import asyncio

import enquest_config as config
from enquest_classify import classify_observations

# Daily webjob entry point. Mirrors main.py's structure for the other
# customer. Runs with force=False, so only cards submitted since the last
# run (i.e. still NULL on both AI fields) get classified.


async def main():
    logging.basicConfig(filename=config.LOG_FILE, level=logging.INFO)
    await classify_observations(force=False)


if __name__ == "__main__":
    asyncio.run(main())
