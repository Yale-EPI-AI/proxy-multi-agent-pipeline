"""Inference engine lifecycle management for vLLM and SGLang."""

import logging
import socket
import subprocess
import time
from abc import ABC, abstractmethod
from io import TextIOWrapper
from pathlib import Path
from subprocess import Popen

logger = logging.getLogger(__name__)


class InferenceEngine(ABC):
    """Base class for managing the lifecycle of an inference engine."""

    def __init__(
        self,
        name: str,
        first_port: int,
        last_port: int,
    ):
        self.name = name
        self.first_port = first_port
        self.last_port = last_port
        self.base_url: str | None = None
        self.process: Popen | None = None
        self.log_fp: TextIOWrapper | None = None

    def is_available_port(self, port: int) -> bool:
        """Check if a port is available on localhost."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", port)) != 0

    def get_available_port(self) -> int | None:
        """Find an available port within the specified range."""
        for port in range(self.first_port, self.last_port + 1):
            if self.is_available_port(port):
                return port
        return None

    @abstractmethod
    def _create_cmd_info(
        self,
        model_id: str,
        host: str,
        port: int,
        args: list[str],
    ) -> tuple[str, list[str]]:
        """Create the command to start the engine and the base URL."""
        pass

    def start(
        self,
        model_id: str,
        args: list[str],
        port: int | None = None,
    ) -> bool:
        """Start the inference engine."""
        host = "localhost"
        name = self.name

        log_dir = Path(f"{name}_logs")
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"{name}_{time.time_ns()}.log"
        self.log_fp = log_path.open("w")

        if port is None:
            port = self.get_available_port()
            if port is None:
                logger.critical(
                    "No available port found in range [%d, %d]",
                    self.first_port,
                    self.last_port,
                )
                return False

        self.base_url, cmd = self._create_cmd_info(model_id, host, port, args)

        logger.info(
            "Starting local inference engine %s on port %d\nLogs: %s\nCommand: %s",
            name,
            port,
            log_path,
            " ".join(cmd),
        )

        self.process = subprocess.Popen(
            cmd,
            stdout=self.log_fp,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        # Wait for the engine to become responsive
        max_wait = 1800
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if self.process.poll() is not None:
                logger.critical("%s terminated abruptly", name)
                self.log_fp.close()
                return False

            try:
                with socket.create_connection((host, port), timeout=1):
                    logger.info("%s is connected and responsive", name)
                    return True
            except (TimeoutError, ConnectionRefusedError, OSError):
                time.sleep(5)

        logger.critical(
            "%s failed to become responsive within %d seconds", name, max_wait
        )
        self.stop()
        return False

    def stop(self):
        """Shut down the inference engine."""
        if not self.process:
            return

        logger.info("Shutting down %s", self.name)
        self.process.terminate()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()

        if self.log_fp:
            self.log_fp.close()

        logger.info("%s has shut down", self.name)


class VLLMEngine(InferenceEngine):
    """vLLM inference engine implementation."""

    def __init__(self, first_port: int = 8000, last_port: int = 8100):
        super().__init__(name="vllm", first_port=first_port, last_port=last_port)

    def _create_cmd_info(
        self,
        model_id: str,
        host: str,
        port: int,
        args: list[str],
    ) -> tuple[str, list[str]]:
        base_url = f"http://{host}:{port}/v1"
        cmd = ["vllm", "serve", model_id, "--host", host, "--port", str(port)] + args
        return base_url, cmd


class SGLangEngine(InferenceEngine):
    """SGLang inference engine implementation."""

    def __init__(self, first_port: int = 8000, last_port: int = 8100):
        super().__init__(name="sglang", first_port=first_port, last_port=last_port)

    def _create_cmd_info(
        self,
        model_id: str,
        host: str,
        port: int,
        args: list[str],
    ) -> tuple[str, list[str]]:
        base_url = f"http://{host}:{port}/v1"
        cmd = [
            "sglang",
            "--model-path",
            model_id,
            "--host",
            host,
            "--port",
            str(port),
        ] + args
        return base_url, cmd
