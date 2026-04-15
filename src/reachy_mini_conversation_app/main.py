"""Entrypoint for the Reachy Mini conversation app."""

import os
import sys
import time
import asyncio
import argparse
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import gradio as gr
from fastapi import FastAPI
from fastrtc import Stream
from gradio.utils import get_space

from reachy_mini import ReachyMini, ReachyMiniApp
from reachy_mini_conversation_app.utils import (
    CameraVisionInitializationError,
    parse_args,
    setup_logger,
    initialize_camera_and_vision,
    log_connection_troubleshooting,
)


def update_chatbot(chatbot: List[Dict[str, Any]], response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Update the chatbot with AdditionalOutputs."""
    chatbot.append(response)
    return chatbot


@dataclass
class RobotAppContext:
    """Runtime context for the selected robot backend."""

    robot: ReachyMini | None
    robot_adapter: Any | None
    robot_runtime: Any
    movement_manager: Any
    head_wobbler: Any
    camera_worker: Any | None = None
    vision_processor: Any | None = None
    is_simulation: bool = False


class NullMovementManager:
    """Minimal no-op movement manager for mock robot mode."""

    def __init__(self) -> None:
        self._listening = False

    def start(self) -> None:
        """Start the movement manager."""

    def stop(self) -> None:
        """Stop the movement manager."""

    def set_listening(self, listening: bool) -> None:
        """Track whether the conversation loop is listening."""
        self._listening = listening

    def is_idle(self) -> bool:
        """Report whether the mock robot is idle enough for idle prompts."""
        return not self._listening

    def set_speech_offsets(self, *_args: Any, **_kwargs: Any) -> None:
        """Ignore speech wobble offsets in mock mode."""


class NullHeadWobbler:
    """Minimal no-op head wobbler for mock robot mode."""

    def start(self) -> None:
        """Start the head wobbler."""

    def stop(self) -> None:
        """Stop the head wobbler."""

    def feed(self, _chunk_b64: str) -> None:
        """Accept a chunk without doing anything."""

    def reset(self) -> None:
        """Reset wobble state."""


def build_robot_runtime(
    *,
    robot: ReachyMini | None = None,
    movement_manager: Any | None = None,
    camera_worker: Any | None = None,
    head_wobbler: Any | None = None,
    vision_processor: Any | None = None,
) -> Any:
    """Build the robot runtime for the configured backend."""
    from reachy_mini_conversation_app.config import config
    from reachy_mini_conversation_app.robot_brain import RobotBrainRuntime, build_robot_adapter

    return RobotBrainRuntime(
        adapter=build_robot_adapter(
            config.ROBOT_BACKEND,
            robot=robot,
            movement_manager=movement_manager,
            camera_worker=camera_worker,
            head_wobbler=head_wobbler,
            vision_processor=vision_processor,
        ),
        default_mode=config.ROBOT_EXECUTION_MODE,
    )


def build_robot_app_context(
    args: argparse.Namespace,
    logger: Any,
    *,
    robot: ReachyMini | None = None,
    robot_runtime: Any | None = None,
) -> RobotAppContext:
    """Build robot-specific runtime dependencies for startup."""
    # Imported lazily so mock mode stays hardware-free.
    from reachy_mini_conversation_app.config import config

    if config.ROBOT_BACKEND == "mock":
        runtime = robot_runtime or build_robot_runtime()
        if not args.gradio:
            logger.info("ROBOT_BACKEND=mock selected. Automatically enabling gradio for the mock-first shell.")
            args.gradio = True
        return RobotAppContext(
            robot=None,
            robot_adapter=getattr(runtime, "adapter", None),
            robot_runtime=runtime,
            movement_manager=NullMovementManager(),
            head_wobbler=NullHeadWobbler(),
            is_simulation=True,
        )

    from reachy_mini_conversation_app.audio.head_wobbler import HeadWobbler
    from reachy_mini_conversation_app.moves import MovementManager

    if robot is None:
        try:
            robot_kwargs = {}
            if args.robot_name is not None:
                robot_kwargs["robot_name"] = args.robot_name

            logger.info("Initializing ReachyMini (SDK will auto-detect appropriate backend)")
            robot = ReachyMini(**robot_kwargs)

        except TimeoutError as e:
            logger.error(f"Connection timeout: Failed to connect to Reachy Mini daemon. Details: {e}")
            log_connection_troubleshooting(logger, args.robot_name)
            sys.exit(1)

        except ConnectionError as e:
            logger.error(f"Connection failed: Unable to establish connection to Reachy Mini. Details: {e}")
            log_connection_troubleshooting(logger, args.robot_name)
            sys.exit(1)

        except Exception as e:
            logger.error(f"Unexpected error during robot initialization: {type(e).__name__}: {e}")
            logger.error("Please check your configuration and try again.")
            sys.exit(1)

    # Auto-enable Gradio in simulation mode (both MuJoCo for daemon and mockup-sim for desktop app)
    status = robot.client.get_status()
    if isinstance(status, dict):
        simulation_enabled = status.get("simulation_enabled", False)
        mockup_sim_enabled = status.get("mockup_sim_enabled", False)
    else:
        simulation_enabled = getattr(status, "simulation_enabled", False)
        mockup_sim_enabled = getattr(status, "mockup_sim_enabled", False)

    is_simulation = simulation_enabled or mockup_sim_enabled

    if is_simulation and not args.gradio:
        logger.info("Simulation mode detected. Automatically enabling gradio flag.")
        args.gradio = True

    try:
        camera_worker, vision_processor = initialize_camera_and_vision(args, robot)
    except CameraVisionInitializationError as e:
        logger.error("Failed to initialize camera/vision: %s", e)
        sys.exit(1)

    movement_manager = MovementManager(
        current_robot=robot,
        camera_worker=camera_worker,
    )
    head_wobbler = HeadWobbler(set_speech_offsets=movement_manager.set_speech_offsets)
    runtime = robot_runtime or build_robot_runtime(
        robot=robot,
        movement_manager=movement_manager,
        camera_worker=camera_worker,
        head_wobbler=head_wobbler,
        vision_processor=vision_processor,
    )
    return RobotAppContext(
        robot=robot,
        robot_adapter=getattr(runtime, "adapter", None),
        robot_runtime=runtime,
        movement_manager=movement_manager,
        head_wobbler=head_wobbler,
        camera_worker=camera_worker,
        vision_processor=vision_processor,
        is_simulation=is_simulation,
    )


def main() -> None:
    """Entrypoint for the Reachy Mini conversation app."""
    args, _ = parse_args()
    run(args)


def run(
    args: argparse.Namespace,
    robot: ReachyMini | None = None,
    app_stop_event: Optional[threading.Event] = None,
    settings_app: Optional[FastAPI] = None,
    instance_path: Optional[str] = None,
    robot_runtime: Any | None = None,
) -> None:
    """Run the Reachy Mini conversation app."""
    from reachy_mini_conversation_app.config import config
    from reachy_mini_conversation_app.console import LocalStream
    from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
    from reachy_mini_conversation_app.providers import (
        get_backend_capabilities,
        get_backend_provider,
        get_configured_api_key,
    )

    logger = setup_logger(args.debug)
    logger.info("Starting Reachy Mini Conversation App")

    if args.no_camera and args.head_tracker is not None:
        logger.warning("Head tracking disabled: --no-camera flag is set. Remove --no-camera to enable head tracking.")

    robot_context = build_robot_app_context(
        args,
        logger,
        robot=robot,
        robot_runtime=robot_runtime,
    )

    deps = ToolDependencies(
        reachy_mini=robot_context.robot,
        movement_manager=robot_context.movement_manager,
        camera_worker=robot_context.camera_worker,
        vision_processor=robot_context.vision_processor,
        head_wobbler=robot_context.head_wobbler,
        robot_runtime=robot_context.robot_runtime,
    )
    current_file_path = os.path.dirname(os.path.abspath(__file__))
    logger.debug(f"Current file absolute path: {current_file_path}")
    chatbot = gr.Chatbot(
        type="messages",
        resizable=True,
        avatar_images=(
            os.path.join(current_file_path, "images", "user_avatar.png"),
            os.path.join(current_file_path, "images", "reachymini_avatar.png"),
        ),
    )
    logger.debug(f"Chatbot avatar images: {chatbot.avatar_images}")

    provider = get_backend_provider()

    if provider == "gemini":
        from reachy_mini_conversation_app.gemini_live import GeminiLiveHandler

        logger.info("Using Gemini Live handler for model: %s", config.MODEL_NAME)
        handler = GeminiLiveHandler(deps, gradio_mode=args.gradio, instance_path=instance_path)
    elif provider == "ollama":
        from reachy_mini_conversation_app.ollama_local import OllamaLocalHandler

        logger.info("Using Ollama local handler for model: %s", config.MODEL_NAME)
        handler = OllamaLocalHandler(deps, gradio_mode=args.gradio, instance_path=instance_path)
    else:
        from reachy_mini_conversation_app.openai_realtime import OpenaiRealtimeHandler

        logger.info("Using OpenAI Realtime handler for model: %s", config.MODEL_NAME)
        handler = OpenaiRealtimeHandler(deps, gradio_mode=args.gradio, instance_path=instance_path)  # type: ignore[assignment]

    stream_manager: gr.Blocks | LocalStream | None = None

    if args.gradio:
        capabilities = get_backend_capabilities()
        api_key_textbox = gr.Textbox(
            label=capabilities.api_key_label or "API Key",
            type="password",
            value=get_configured_api_key() if not get_space() else "",
            visible=capabilities.requires_api_key,
        )

        from reachy_mini_conversation_app.gradio_personality import PersonalityUI

        personality_ui = PersonalityUI()
        personality_ui.create_components()

        stream = Stream(
            handler=handler,
            mode="send-receive",
            modality="audio",
            additional_inputs=[
                chatbot,
                api_key_textbox,
                *personality_ui.additional_inputs_ordered(),
            ],
            additional_outputs=[chatbot],
            additional_outputs_handler=update_chatbot,
            ui_args={"title": "Talk with Reachy Mini"},
        )
        stream_manager = stream.ui
        if not settings_app:
            app = FastAPI()
        else:
            app = settings_app

        personality_ui.wire_events(handler, stream_manager)

        app = gr.mount_gradio_app(app, stream.ui, path="/")
    else:
        # In headless mode, wire settings_app + instance_path to console LocalStream
        stream_manager = LocalStream(
            handler,
            robot_context.robot,
            settings_app=settings_app,
            instance_path=instance_path,
        )

    # Each async service → its own thread/loop
    robot_context.movement_manager.start()
    robot_context.head_wobbler.start()
    if robot_context.camera_worker:
        robot_context.camera_worker.start()

    def poll_stop_event() -> None:
        """Poll the stop event to allow graceful shutdown."""
        if app_stop_event is not None:
            app_stop_event.wait()

        logger.info("App stop event detected, shutting down...")
        try:
            stream_manager.close()
        except Exception as e:
            logger.error(f"Error while closing stream manager: {e}")

    if app_stop_event:
        threading.Thread(target=poll_stop_event, daemon=True).start()

    try:
        stream_manager.launch()
    except KeyboardInterrupt:
        logger.info("Keyboard interruption in main thread... closing server.")
    finally:
        robot_context.movement_manager.stop()
        robot_context.head_wobbler.stop()
        if robot_context.camera_worker:
            robot_context.camera_worker.stop()

        if robot_context.robot is not None:
            # Ensure media is explicitly closed before disconnecting
            try:
                robot_context.robot.media.close()
            except Exception as e:
                logger.debug(f"Error closing media during shutdown: {e}")

            # prevent connection to keep alive some threads
            robot_context.robot.client.disconnect()
            time.sleep(1)
        logger.info("Shutdown complete.")


class ReachyMiniConversationApp(ReachyMiniApp):  # type: ignore[misc]
    """Reachy Mini Apps entry point for the conversation app."""

    custom_app_url = "http://0.0.0.0:7860/"
    dont_start_webserver = False

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        """Run the Reachy Mini conversation app."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        args, _ = parse_args()

        # is_wireless = reachy_mini.client.get_status()["wireless_version"]
        # args.head_tracker = None if is_wireless else "mediapipe"

        instance_path = self._get_instance_path().parent
        run(
            args,
            robot=reachy_mini,
            app_stop_event=stop_event,
            settings_app=self.settings_app,
            instance_path=instance_path,
        )


if __name__ == "__main__":
    app = ReachyMiniConversationApp()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
