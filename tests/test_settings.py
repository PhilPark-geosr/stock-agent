from app.core.settings import _ENV_FILE, _PROJECT_ROOT


def test_environment_file_points_to_project_root():
    assert _PROJECT_ROOT.name == "stock-agent"
    assert _ENV_FILE == _PROJECT_ROOT / ".env"
