from pydantic import BaseModel
from slack_sdk.web.async_client import AsyncWebClient

from typing import Dict, Any


class BotContext(BaseModel):
    client: Any = None


class UserContext(BaseModel):
    slack_id: str
    slack_name: str


class ChannelContext(BaseModel):
    channel_id: str | None = None
    channel_name: str | None = None


class ActionContext(BaseModel):
    bot: BotContext
    input: Dict[str, Any] = {}
    user: UserContext
    channel: ChannelContext | None = None

    template_name: str
    step_id: str


def make_context(
    user: Dict[str, Any] = {},
    channel: Dict[str, Any] = {},
    template_name: str = None,
    step_id: str = None,
    input: Dict[str, Any] = {},
) -> ActionContext:
    from bot_app import app

    return ActionContext(
        bot=BotContext(client=app.client),
        template_name=template_name,
        step_id=step_id,
        input=input,
        user=UserContext(**user),
        channel=ChannelContext(**channel),
    )
