import logging
import asyncio
from typing import List, Any, Dict
from models import WorkflowState, WorkflowStatus
from plugin_manager import plugins
from database import session_maker
from uuid import uuid4
from context import make_context
from template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class WorkflowStateNotFound(Exception):
    pass


class WorkflowStateManager:
    def __init__(self):
        self._workflow_id = None
        self._tasks = None
        self._initial_data: Dict[str, Any] = {}
        self._output: Dict[str, Dict] = {}

    @property
    def workflow_id(self):
        return self._workflow_id

    @property
    def tasks(self):
        return self._tasks

    @property
    def initial_data(self):
        return self._initial_data

    @property
    def output(self):
        return self._output

    async def create_state(
        self, workflow_id: str, tasks: List[Dict], initial_data: Any
    ):
        async with session_maker() as session:
            record = WorkflowState(
                workflow_id=workflow_id,
                tasks=tasks,
                initial_data=initial_data,
                output={},
                status=WorkflowStatus.ACTIVE,
            )
            self._workflow_id = workflow_id
            self._tasks = tasks
            self._initial_data = initial_data
            session.add(record)
            await session.commit()

    async def update_state(self, workflow_id: str, task_index: int, data: str):
        async with session_maker() as session:
            record = await session.get(WorkflowState, workflow_id)
            if record:
                record.current_task_index = task_index
                record.output = data
                self._output = data
                await session.commit()
            else:
                raise WorkflowStateNotFound(
                    f"Workflow with id {workflow_id} not found."
                )

    async def mark_as_completed(self, workflow_id: str):
        async with session_maker() as session:
            record = await session.get(WorkflowState, self.workflow_id)
            if record:
                record.status = WorkflowStatus.COMPLETED
                await session.commit()
            else:
                raise WorkflowStateNotFound(
                    f"Workflow with id {workflow_id} not found."
                )

    async def get_status(self, workflow_id: str) -> WorkflowStatus:
        async with session_maker() as session:
            record = await session.get(WorkflowState, workflow_id)
            if record:
                return record.status
            else:
                raise WorkflowStateNotFound(
                    f"Workflow with id {workflow_id} not found."
                )


class Workflow:
    def __init__(
        self,
        current_task_index: int = 0,
        state_manager: WorkflowStateManager = None,
        template_renderer: TemplateRenderer = None,
    ):
        self.current_task_index = current_task_index
        self._state = state_manager
        self._template_renderer = template_renderer

    async def check_cancelled(self) -> bool:
        return (
            await self._state.get_status(self.workflow_id) == WorkflowStatus.CANCELLED
        )

    async def monitor_cancellation(self, main_task: asyncio.Task):
        try:
            while True:
                await asyncio.sleep(1)
                if await self.check_cancelled():
                    logger.info(
                        f"Workflow {self.workflow_id} detected cancellation. Cancelling main task."
                    )
                    main_task.cancel()
                    return
        except asyncio.CancelledError:
            return

    async def run(self):
        main_task = asyncio.current_task()
        cancellation_monitor = asyncio.create_task(self.monitor_cancellation(main_task))
        try:
            while self.current_task_index < len(self._state.tasks):
                task = self._state.tasks[self.current_task_index]
                plugin_name = task["plugin"]
                try:
                    ctx_input = await self._template_renderer.render_object(
                        task["input"],
                        self._state.initial_data | {"output": self._state.output},
                    )
                    user = self._state.initial_data["body"].get("user", {})
                    channel = self._state.initial_data["body"].get("channel", {})
                    ctx = make_context(
                        user={
                            "slack_id": user.get("id"),
                            "slack_name": user.get("name"),
                        },
                        channel=channel,
                        template_name="dummy",
                        step_id=task["id"],
                        input=ctx_input,
                    )
                    output = self._state.output
                    output[task["id"]] = await plugins.run_plugin(plugin_name, ctx)
                    self.current_task_index += 1
                    await self._state.update_state(
                        self._state.workflow_id, self.current_task_index, output
                    )
                except asyncio.CancelledError:
                    logger.info(
                        f"Workflow {self.workflow_id} received cancellation during task execution."
                    )
                    raise

            logger.info(f"Workflow {self._state.workflow_id} completed")
            await self._state.mark_as_completed(self._state.workflow_id)
        except asyncio.CancelledError:
            logger.info(f"Workflow {self._state.workflow_id} cancelled.")
            raise
        except Exception as e:
            logger.error(f"Workflow {self._state.workflow_id} failed with error: {e}")
            logger.exception(e)
        finally:
            cancellation_monitor.cancel()


async def run_workflow(tasks: List[str], initial_data: Any):
    workflow_id = str(uuid4())
    state_manager = WorkflowStateManager()
    await state_manager.create_state(workflow_id, tasks, initial_data)
    template_renderer = TemplateRenderer()
    workflow = Workflow(
        state_manager=state_manager,
        template_renderer=template_renderer,
    )
    logger.info(f"Starting workflow {workflow_id}")
    asyncio.create_task(workflow.run())
    return workflow_id
