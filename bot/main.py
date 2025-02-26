import asyncio
import argparse
import logging
from template_loader import periodic_fetch
from bot_config import settings
from bot_app import start_app, templates_registry
from datasource.registry import DataSourceRegistry
from plugin_manager import plugins
from logging_config import setup_logging
from database import engine
from models import Base


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Application configuration")
    parser.add_argument(
        "--config", required=True, help="Path to the YAML configuration file"
    )
    parser.add_argument(
        "--log-mode",
        default="json",
        choices=["json", "color"],
        help="Logging format mode (default: json)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def register_external_datasources(data_sources_config) -> None:
    from datasource.ext.jira_datasource import JiraIssuesRepository

    if "jira" in data_sources_config:
        jira_config = data_sources_config["jira"]
        jira_ds = JiraIssuesRepository(**jira_config)
        DataSourceRegistry.register_source("jira-issues", jira_ds)


async def main() -> None:
    # Temporary workaround to create the database tables.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Parse command-line arguments.
    args = parse_args()

    # Configure logging.
    setup_logging(log_mode=args.log_mode, level=args.log_level)
    logging.info("Starting application with config file: %s", args.config)

    logging.debug("Debug Mode: %s", settings.debug)
    asyncio.ensure_future(
        periodic_fetch(
            settings.templates_importer, templates_registry.register_template
        )
    )

    logging.info("Loading plugins.")
    plugins.load_plugins(settings.plugins)

    logging.info("Registering external data sources.")
    register_external_datasources(settings.datasources)

    logging.info("Running the bot app.")
    await start_app()


if __name__ == "__main__":
    asyncio.run(main())
