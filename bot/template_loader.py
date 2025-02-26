import asyncio
import aiohttp
import aiofiles
import yaml
import logging
import hashlib
from typing import Tuple, Any, Callable, Awaitable
from bot_config import TemplatesImporterSettings

logger = logging.getLogger(__name__)


# === Strategy Pattern for Location Reading ===


class BaseLocationStrategy:
    async def read(
        self, target: str, session: aiohttp.ClientSession = None
    ) -> Tuple[str, Any]:
        """
        Reads the content from the given target and returns a tuple of
        (raw_text, parsed_yaml). Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement this method.")


class FileStrategy(BaseLocationStrategy):
    async def read(
        self, target: str, session: aiohttp.ClientSession = None
    ) -> Tuple[str, Any]:
        """
        Reads a local file asynchronously.
        """
        try:
            async with aiofiles.open(target, mode="r", encoding="utf-8") as f:
                raw_text = await f.read()
            data = yaml.safe_load(raw_text)
            logger.debug(f"Successfully read YAML from file {target}.")
            return raw_text, data
        except Exception as e:
            logger.error(f"Error reading YAML from file {target}: {e}")
            raise


class UrlStrategy(BaseLocationStrategy):
    async def read(
        self, target: str, session: aiohttp.ClientSession = None
    ) -> Tuple[str, Any]:
        """
        Fetches a YAML file from a URL asynchronously.
        """
        if session is None:
            raise ValueError("HTTP session is required for URL reading.")
        try:
            async with session.get(target) as response:
                response.raise_for_status()
                raw_text = await response.text()
            data = yaml.safe_load(raw_text)
            logger.debug(f"Successfully fetched YAML from URL {target}.")
            return raw_text, data
        except Exception as e:
            logger.error(f"Error fetching YAML from URL {target}: {e}")
            raise


# Mapping location type to corresponding strategy instance
STRATEGIES = {"file": FileStrategy(), "url": UrlStrategy()}


async def fetch_yaml(
    location_item: dict, session: aiohttp.ClientSession = None
) -> Tuple[str, Any]:
    """
    Uses the appropriate strategy to fetch and parse YAML content based on the location item.

    Returns:
        A tuple (raw_text, data) on success.
    """
    location_type = location_item.get("type", "").lower()
    target = location_item.get("target")

    if not location_type or not target:
        logger.error(f"Invalid location item: {location_item}")
        return None, None

    strategy = STRATEGIES.get(location_type)
    if not strategy:
        logger.error(f"Unknown location type: {location_type} for target {target}")
        return None, None

    try:
        # For URL strategy, the session must be provided.
        result = await strategy.read(target, session=session)
        return result
    except Exception as e:
        logger.error(f"Error processing {target}: {e}")
        return None, None


def compute_hash(text: str) -> str:
    """
    Computes an MD5 hash for the given text.
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()


async def periodic_fetch(
    config: TemplatesImporterSettings,
    yaml_handler: Callable[[dict], Awaitable[Any]] = None,
):
    """
    Periodically fetches YAML files from the locations specified in the configuration.
    Calls the handler only if the content has changed since the last read.

    The configuration should be a dictionary with keys:
      - interval: time interval (in seconds) between fetch cycles.
      - locations: a list of location items.

    Args:
        config (dict): Configuration dictionary.
        yaml_handler (callable, optional): A function to process the loaded YAML data.
            It should accept two arguments: the parsed YAML data and the location item.
    """
    interval = config.interval
    locations = config.locations

    if not isinstance(locations, list) or not locations:
        logger.error(
            "The 'locations' field must be a non-empty list in the configuration."
        )
        return

    # Dictionary to store the previous hash for each target
    previous_hashes = {}

    async with aiohttp.ClientSession() as session:
        while True:
            # logger.info("Starting a new fetch cycle.")
            tasks = [fetch_yaml(item, session) for item in locations]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for location_item, result in zip(locations, results):
                target = location_item.get("target", "unknown")

                # If an exception was returned or result is None, skip processing
                if isinstance(result, Exception) or result is None:
                    logger.error(f"Failed to retrieve data from {target}.")
                    continue

                raw_text, data = result
                if raw_text is None:
                    logger.error(f"No text content retrieved from {target}.")
                    continue

                new_hash = compute_hash(raw_text)
                old_hash = previous_hashes.get(target)

                if old_hash == new_hash:
                    logger.debug(f"No changes detected in {target}.")
                else:
                    logger.info(f"Change detected in {target}.")
                    previous_hashes[target] = new_hash
                    if yaml_handler:
                        try:
                            handler_result = yaml_handler(data)
                            if asyncio.iscoroutine(handler_result):
                                await handler_result
                        except Exception as e:
                            logger.error(f"Error in YAML handler for {target}: {e}")

            # logger.info(f"Waiting for {interval} seconds before the next cycle...\n")
            await asyncio.sleep(interval)
