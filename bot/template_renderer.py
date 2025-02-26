from jinja2 import BaseLoader, Environment, select_autoescape
from datasource.registry import DataSourceRegistry
from jinja2 import nodes
from jinja2.ext import Extension
import json

from typing import Any, Dict


class TemplateRenderer:
    def __init__(self):
        self._env = Environment(
            loader=BaseLoader(),
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=True,
            variable_start_string="((",
            variable_end_string="))",
        )
        self._env.globals["fetch"] = jinja_fetch

    async def render_object(self, obj: Any, context: Dict[str, Any]) -> str:
        json_string = json.dumps(obj)
        rendered_string = await self.render_template(json_string, context)
        return json.loads(rendered_string)

    async def render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        template = self._env.from_string(template_str)
        return await template.render_async(context)


async def jinja_fetch(
    source_name: str, filters: Dict[str, Any] | None = None, **kwargs: Any
) -> Any:
    source = await DataSourceRegistry.get_source(source_name)
    result = await source.fetch(filters, **kwargs)
    return result
