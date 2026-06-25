from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
SIM_ROOT = BACKEND_ROOT.parent
PROJECT_ROOT = SIM_ROOT.parent

SESSIONS_ROOT = SIM_ROOT / "sessions"
DEFAULT_SESSION_DIR = SESSIONS_ROOT / "danganronpav3"

ENVIRONMENT_ROOT = PROJECT_ROOT / "environment"
FRONTEND_SERVER_ROOT = ENVIRONMENT_ROOT / "frontend_server"


def backend_path(*parts):
    return BACKEND_ROOT.joinpath(*parts)


def project_path(*parts):
    return PROJECT_ROOT.joinpath(*parts)


def resolve_backend_file(path):
    path = Path(path)
    if path.is_absolute():
        return path
    return BACKEND_ROOT / path
