import yaml
import logging
from pathlib import Path
import argparse
from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


from typing import List, Dict, Any, Tuple, Type

logger = logging.getLogger(__name__)


class ArgsYamlConfigSettingsSource(PydanticBaseSettingsSource):

    def __init__(self, settings_cls: Type[BaseSettings]) -> None:
        super().__init__(settings_cls)

    def _parse_args(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        parser.add_argument("--config", required=True)
        return parser.parse_known_args()[0]

    def get_field_value(self, field, field_name):
        return super().get_field_value(field, field_name)

    def __call__(self) -> Dict[str, Any]:
        args = self._parse_args()
        path = Path(args.config)
        if path.exists():
            try:
                with path.open("r", encoding=self.config.get("env_file_encoding")) as f:
                    data = yaml.safe_load(f)
                    return data if data is not None else {}
            except Exception as e:
                logger.error(
                    "Error reading YAML configuration file '%s': %s",
                    self.yaml_config_path,
                    e,
                )
                raise ValueError(
                    f"Error reading YAML configuration file '{self.yaml_config_path}': {e}"
                ) from e
        else:
            raise FileNotFoundError(
                f"YAML configuration file '{self.yaml_config_path}' does not exist"
            )


class TemplatesImporterSettings(BaseSettings):
    interval: int
    locations: List[Dict[str, Any]]


class Plugins(BaseSettings):
    name: str
    path: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="allow")

    debug: bool = Field(False, env="DEBUG")
    bot_token: str = Field(..., env="BOT_TOKEN")
    app_token: str = Field(..., env="APP_TOKEN")
    templates_importer: TemplatesImporterSettings = Field(...)
    plugins_path: str = Field(..., env="PLUGINS_PATH")
    plugins: List[Plugins] = Field(...)

    # Data sources
    datasources: Dict[str, Dict[str, Any]] = Field(...)

    # Database settings
    database_url: str = Field(..., env="DATABASE_URL")
    db_echo: bool = Field(False, env="DB_ECHO")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            dotenv_settings,
            env_settings,
            ArgsYamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings: Settings = Settings()
