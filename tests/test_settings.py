from app.core.settings import _ENV_FILE, _PROJECT_ROOT


def test_environment_file_points_to_project_root():
    assert (_PROJECT_ROOT / "pyproject.toml").is_file()
    assert (_PROJECT_ROOT / "app" / "core" / "settings.py").is_file()
    assert _ENV_FILE == _PROJECT_ROOT / ".env"
