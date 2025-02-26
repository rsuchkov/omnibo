import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
from typing import List, Protocol
from abc import ABC, abstractmethod
from bot_config import settings

logger = logging.getLogger(__name__)


class PluginDescriptor(Protocol):
    name: str
    path: str


class Plugin(ABC):
    @abstractmethod
    async def run(self, *args, **kwargs) -> dict:
        pass


class PythonPlugin(Plugin):
    def __init__(self, module_name: str, file_path: str):
        self.module_name = module_name
        self.file_path = file_path
        self.module = self._load_module()

    def _load_module(self):
        path = Path(self.file_path)
        # If the path is a directory and contains __init__.py, treat it as a package
        if path.is_dir() and (path / "__init__.py").exists():
            init_file = str(path / "__init__.py")
            spec = importlib.util.spec_from_file_location(self.module_name, init_file)
        elif path.is_file() and self.file_path.endswith(".py"):
            spec = importlib.util.spec_from_file_location(
                self.module_name, self.file_path
            )
        else:
            raise ImportError(f"Cannot load Python plugin from {self.file_path}")
        if spec is None or spec.loader is None:
            raise ImportError(
                f"Cannot load module {self.module_name} from {self.file_path}"
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    async def run(self, *args, **kwargs) -> dict:
        if not hasattr(self.module, "run"):
            raise AttributeError(
                f"Module '{self.module_name}' does not have a 'run' function"
            )
        result = self.module.run(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result


# Executable plugin implementation
class ExecutablePlugin(Plugin):
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def run(self, *args, **kwargs) -> dict:
        # Convert positional arguments to strings
        args_list = [str(arg) for arg in args]
        process = await asyncio.create_subprocess_exec(
            self.file_path,
            *args_list,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error_message = stderr.decode().strip()
            raise RuntimeError(
                f"Executable plugin '{self.file_path}' exited with error: {error_message}"
            )
        try:
            return json.loads(stdout.decode())
        except json.JSONDecodeError as e:
            raise ValueError(f"Output from '{self.file_path}' is not valid JSON: {e}")


class PluginManager:
    def __init__(self, base_path: Path):
        """
        :param base_path: Base directory to resolve relative plugin paths.
        """
        self.base_path = base_path
        self.plugins = {}

    def load_plugins(self, plugins: List[PluginDescriptor]):
        for descriptor in plugins:
            try:
                name = getattr(descriptor, "name")
                rel_path = getattr(descriptor, "path")
            except AttributeError as e:
                logger.error(
                    f"Plugin descriptor {descriptor} is missing required attribute: {e}"
                )
                continue

            file_path = str((self.base_path / rel_path).resolve())
            try:
                path_obj = Path(file_path)
                if (path_obj.is_file() and file_path.endswith(".py")) or (
                    path_obj.is_dir() and (path_obj / "__init__.py").exists()
                ):
                    plugin = PythonPlugin(module_name=name, file_path=file_path)
                    self.plugins[name] = plugin
                    logger.info(f"Loaded Python plugin: {name}")
                elif os.access(file_path, os.X_OK):
                    plugin = ExecutablePlugin(file_path=file_path)
                    self.plugins[name] = plugin
                    logger.info(f"Loaded Executable plugin: {name}")
                else:
                    logger.error(
                        f"Plugin '{name}' at {file_path} is neither a valid Python plugin nor an executable file."
                    )
            except Exception as e:
                logger.error(f"Failed to load plugin '{name}': {e}")

    async def run_plugin(self, name: str, *args, **kwargs) -> dict:
        plugin = self.plugins.get(name)
        if plugin is None:
            raise ValueError(f"Plugin '{name}' not found")
        return await plugin.run(*args, **kwargs)


plugins = PluginManager(Path(settings.plugins_path))
