from .camera import DesktopCameraSource, default_camera_source, describe_camera_source
from .events import PERCEPTION_EVENT_TYPES, build_scene_annotations, build_scene_request, normalize_engagement

__all__ = [
    "DesktopCameraSource",
    "PERCEPTION_EVENT_TYPES",
    "PerceptionService",
    "build_perception_service",
    "build_scene_annotations",
    "build_scene_request",
    "default_camera_source",
    "describe_camera_source",
    "normalize_engagement",
    "resolve_default_perception_mode",
]


def __getattr__(name: str):
    if name in {"PerceptionService", "build_perception_service", "resolve_default_perception_mode"}:
        from .perception import PerceptionService, build_perception_service, resolve_default_perception_mode

        return {
            "PerceptionService": PerceptionService,
            "build_perception_service": build_perception_service,
            "resolve_default_perception_mode": resolve_default_perception_mode,
        }[name]
    raise AttributeError(name)
