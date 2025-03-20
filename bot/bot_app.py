import re
import json
import logging
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from bot_config import settings
from typing import Dict, Any, List, Callable
from hashlib import sha256
from workflow import run_workflow
from template_renderer import TemplateRenderer


logger = logging.getLogger(__name__)

app: AsyncApp = AsyncApp(token=settings.bot_token, logger=logger)


async def start_app() -> None:
    handler: AsyncSocketModeHandler = AsyncSocketModeHandler(app, settings.app_token)
    await handler.start_async()


class SlackValuesParser:

    @staticmethod
    def parse_values(state_values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts state["values"] from Slack into a structured dictionary key: value.

        :param state_values: dict - state["values"] object from Slack view
        :return: dict - transformed dictionary
        """
        parsed_data: Dict[str, Dict[str, Any]] = {}

        for block_id, actions in state_values.items():
            if block_id not in parsed_data:
                parsed_data[block_id] = {}

            for action_id, action_data in actions.items():
                if "value" in action_data:
                    parsed_data[block_id][action_id] = action_data["value"]
                elif "selected_option" in action_data:
                    parsed_data[block_id][action_id] = action_data["selected_option"][
                        "value"
                    ]
                elif "selected_options" in action_data:
                    parsed_data[block_id][action_id] = [
                        opt["value"] for opt in action_data["selected_options"]
                    ]
                elif "selected_date" in action_data:
                    parsed_data[block_id][action_id] = action_data["selected_date"]
                elif "selected_time" in action_data:
                    parsed_data[block_id][action_id] = action_data["selected_time"]
                else:
                    parsed_data[block_id][action_id] = action_data

        return parsed_data


def modify_dict_values(data, keys_to_modify: set, prefix: str):
    def recursive_modify(d):
        if isinstance(d, dict):
            for key, value in d.items():
                if key in keys_to_modify and isinstance(value, str):
                    d[key] = prefix + value
                else:
                    recursive_modify(value)
        elif isinstance(d, list):
            for item in d:
                recursive_modify(item)

    recursive_modify(data)
    return data


class ScreensOrchestrator:
    def __init__(
        self,
        template_name: str,
        form: Dict[str, Any],
        renderer: TemplateRenderer = TemplateRenderer(),
    ):
        self._template_name = template_name
        self._form = form
        self._renderer = renderer

    def _draw_progressbar_blocks(self, current_screen: int, total_screens: int) -> Dict:
        finished = "🟩 " * current_screen
        current = "⬜ " * (total_screens - current_screen)
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Workflow Progress"},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"{finished}{current}*(Step {current_screen} of {total_screens})*",
                    }
                ],
            },
        ]

    async def render(
        self, screen_index: int, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        screen = self._form["screens"][screen_index]
        blocks = (await self._renderer.render_object(screen, context))["blocks"]
        if len(self._form["screens"]) > 1:
            blocks = (
                self._draw_progressbar_blocks(
                    screen_index + 1, len(self._form["screens"])
                )
                + blocks
            )
        view = {
            "type": "modal",
            "callback_id": self._form["callback_id"],
            "title": self._form["title"],
            "blocks": blocks,
            "close": {"type": "plain_text", "text": "Close"},
            "submit": self._form["submit"],
        }
        if screen_index == len(self._form["screens"]) - 1:
            view["submit"] = self._form["submit"]
        else:
            # save private metadata about the current screen
            view["private_metadata"] = json.dumps(
                {
                    "current_screen": screen_index,
                    "total_screens": len(self._form["screens"]),
                    "template_name": self._template_name,
                }
            )
            view["callback_id"] = f"next_step_modal"
            view["submit"] = {"type": "plain_text", "text": "Next"}
            # blocks.append(
            #     {
            #         "type": "actions",
            #         "elements": [
            #             {
            #                 "type": "button",
            #                 "text": {"type": "plain_text", "text": "Next"},
            #                 "style": "primary",
            #                 "action_id": "next_step_modal",
            #             }
            #         ],
            #     }
            # )
        return view


class ModalScreen:
    def __init__(
        self,
        template_name: str,
        screen: Dict,
        renderer: TemplateRenderer = TemplateRenderer(),
    ):
        self._template_name = template_name
        self._screen = modify_dict_values(
            screen, {"action_id", "callback_id"}, self._template_name
        )
        self._renderer = renderer

    async def render(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return await self._renderer.render_object(self._screen, context)


class MessageScreen:
    def __init__(
        self,
        template_name: str,
        screen: Dict,
        renderer: TemplateRenderer = TemplateRenderer(),
    ):
        self._template_name = template_name
        self._screen = modify_dict_values(
            screen, {"action_id1", "callback_id1"}, self._template_name
        )
        self._renderer = renderer

    async def render(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return await self._renderer.render_object(self._screen, context)


class AppHandler:
    def __init__(self, renderer: TemplateRenderer = TemplateRenderer()) -> None:
        self._templates: Dict[str, Dict] = {}
        self._views_submissions: Dict[str, List[Dict]] = {}
        self._actions: Dict[str, List[Dict]] = {}
        self._renderer = renderer
        self._forms: Dict[str, ScreensOrchestrator] = {}

        # register common handlers
        app.view("next_step_modal")(self.next_step_modal)

    async def run_workflow(self, template_name: str) -> None:
        pass

    async def proxy_view_submission(
        self,
        ack: Callable,
        body: Dict[str, Any],
        view: Dict[str, Any],
        say: Callable,
    ) -> None:
        await ack()
        callback_id = view["callback_id"]
        form_data = SlackValuesParser.parse_values(view["state"]["values"])
        await run_workflow(
            tasks=self._views_submissions[callback_id],
            initial_data={
                "view": view,
                "body": body,
                "values": form_data,
            },
        )

    async def proxy_action(self, ack: Callable, body: Dict[str, Any], client) -> None:
        await ack()
        message_ts = body["message"]["ts"]
        values = body["state"]["values"]
        action_id = body["actions"][0]["action_id"]

    @app.action("next_step")
    async def next_step(self, ack: Callable, body: Dict[str, Any], client) -> None:
        await ack()

    # @app.view("next_step_modal")
    async def next_step_modal(
        self,
        ack: Callable,
        body: Dict[str, Any],
        client: Any,
        view: Dict[str, Any],
    ) -> None:
        await ack()
        private_metadata = json.loads(view["private_metadata"])
        template_name = private_metadata["template_name"]
        current_screen = private_metadata["current_screen"]
        total_screens = private_metadata["total_screens"]
        logger.info(f"Private metadata: {private_metadata}")
        workflow_form = self._forms.get(template_name)
        view = await workflow_form.render(current_screen + 1, {})
        # view = await self._renderer.render_object(view, {})
        await client.views_open(trigger_id=body["trigger_id"], view=view)

    def register_view_submission(
        self, template_name: str, callback_id: str, steps: List[Dict]
    ) -> None:

        if callback_id not in self._views_submissions:
            app.view(callback_id)(self.proxy_view_submission)
        else:
            logger.warning(f"Callback ID {callback_id} already exists. Overwriting.")
        self._views_submissions[callback_id] = steps

    def register_action(
        self, template_name: str, action_id: str, steps: List[Dict]
    ) -> None:
        # modified_action_id = f"{template_name}_{action_id}"
        modified_action_id = action_id  # TODO: Link action_id to template_name
        if modified_action_id not in self._actions:
            app.action(modified_action_id)(self.proxy_action)
        else:
            logger.warning(f"Action ID {action_id} already exists. Overwriting")
        self._actions[modified_action_id] = steps

    def register_screens(self, template_name: str, template: Dict[str, Any]) -> None:
        workflow_form = template["spec"].get("form")
        if workflow_form is None:
            return
        self._forms[template_name] = ScreensOrchestrator(template_name, workflow_form)

    def register_workflow_handlers(
        self, template_name: str, template: Dict[str, Any]
    ) -> None:

        # Registering actions described in the template
        for action in template["spec"].get("actions", []):
            action_id = action["id"]
            steps = action["steps"]
            self.register_action(template_name, action_id, steps)

        # Registering view submissions described in the template
        for view_submission in template["spec"].get("view_submissions", []):
            callback_id = view_submission["id"]
            steps = view_submission["steps"]
            self.register_view_submission(template_name, callback_id, steps)

    def register_screens_handlers(
        self, template_name: str, template: Dict[str, Any]
    ) -> None:
        # Method that is overridden in subclasses to register handlers
        # responsible for handling "display" events of messages and modals
        pass

    def register_template(self, template: Dict[str, Any]) -> None:
        template_name = template["metadata"]["name"]
        self._templates[template_name] = template

        # Registering screens described in the template
        self.register_screens(template_name, template)

        self.register_workflow_handlers(template_name, template)
        self.register_screens_handlers(template_name, template)


class ShortcutHandler(AppHandler):
    def __init__(self, renderer: TemplateRenderer = TemplateRenderer()) -> None:
        super().__init__(renderer)
        self._shortcuts: Dict[str, str] = {}

    async def proxy_shortcut(self, ack, body, client, template: str) -> None:
        await ack()
        # shortcut_name = body["callback_id"]
        # view = self._templates[shortcut_name]["spec"]["view"]
        # view["callback_id"] = self._shortcuts[shortcut_name]
        workflow_form = self._forms.get(template)
        view = await workflow_form.render(0, {})
        # view = await self._renderer.render_object(view, {})
        await client.views_open(trigger_id=body["trigger_id"], view=view)

    def register_screens_handlers(
        self, template_name: str, template: Dict[str, Any]
    ) -> None:
        if template_name not in self._shortcuts:
            # self._shortcuts[template_name] = (
            #     f"{template_name}_{template["spec"]["view"]["callback_id"]}"
            # )
            self._shortcuts[template_name] = 1

            async def callback(ack, body, client):
                return await self.proxy_shortcut(ack, body, client, template_name)

            app.shortcut(template_name)(callback)
            logger.info(
                f"Registerd handler for template: {template_name} with type: shortcut"
            )


class EventHandler(AppHandler):
    def __init__(
        self, event_type: str, renderer: TemplateRenderer = TemplateRenderer()
    ) -> None:
        super().__init__(renderer)
        self._event_type = event_type
        self._patterns: Dict[str, Dict] = {}
        app.event(event_type)(self.proxy_event)

    def _find_template(self, text: str) -> Dict[str, Any] | None:
        for pattern, template in self._patterns.items():
            if re.match(pattern, text):
                return template

    async def proxy_event(self, event, say) -> None:
        text = event["text"]
        template = self._find_template(text)
        if template is None:
            logger.debug(f"No template found for event: {text}")
            return
        event_ts = event["event_ts"]
        channel = event.get("channel")
        view = template["spec"]["view"]
        view = await self._renderer.render_object(view, {})
        await say(text="Test", blocks=view["blocks"])

    def register_screens_handlers(
        self, template_name: str, template: Dict[str, Any]
    ) -> None:
        pattern = template["spec"]["pattern"]
        if pattern not in self._patterns:
            self._patterns[pattern] = template
            logger.info(
                f"Registerd handler for template: {template_name} with type: {self._event_type}"
            )


class AppMentionHandler(EventHandler):
    def __init__(self, renderer: TemplateRenderer = TemplateRenderer()) -> None:
        super().__init__("app_mention", renderer)

    def _find_template(self, text: str) -> Dict[str, Any] | None:
        clean_text = re.sub(r"^<@[\w\d]+>\s*", "", text)
        return super()._find_template(clean_text)


class TemplatesRegistry:
    def __init__(self) -> None:
        self._handlers = {
            "shortcut": ShortcutHandler(),
            "app_mention": AppMentionHandler(),
        }

    async def register_template(self, template: Dict[str, Any]) -> None:
        handler_type = template["spec"]["type"]
        handler = self._handlers.get(handler_type)
        if handler is None:
            logger.error(
                f"Unsupported template type: {handler_type}. Available types: {self._handlers.keys()}"
            )
            return
        handler.register_template(template)


templates_registry = TemplatesRegistry()
