from pathlib import Path


def test_segregated_repository_layout() -> None:
    """Verifies the segregated frontend/, backend/, hardware/, and docs/ repository layout."""
    backend_dir = Path(__file__).resolve().parent.parent
    root = backend_dir.parent

    # 1. Segregated top-level tiers
    for directory in ["frontend", "backend", "hardware", "docs"]:
        dir_path = root / directory
        assert dir_path.is_dir(), f"Expected top-level directory '{directory}' missing from repository"

    # 2. Frontend structure
    assert (root / "frontend" / "package.json").is_file()
    assert (root / "frontend" / "src" / "App.tsx").is_file()

    # 3. Self-contained backend + ULTRON structure
    for subdir in ["fastapi", "ultron", "ultron_stub", "configs", "tests"]:
        assert (backend_dir / subdir).is_dir(), f"Expected backend/'{subdir}' missing"

    expected_ultron_dirs = [
        "planner",
        "memory",
        "world_model",
        "replanner",
        "vision",
        "communication",
        "safety",
        "simulation",
    ]
    for subdir in expected_ultron_dirs:
        dir_path = backend_dir / "ultron" / subdir
        assert dir_path.is_dir(), f"Expected backend/ultron/'{subdir}' missing"

    # 4. Isolated hardware tier (SCOUT01, HAWK01, ESP32 firmware)
    for subdir in ["navigation", "sensors", "communication"]:
        assert (root / "hardware" / "scout" / subdir).is_dir()

    for subdir in ["flight_interface", "sensors", "communication"]:
        assert (root / "hardware" / "hawk" / subdir).is_dir()

    for subdir in ["motors", "sensors", "safety"]:
        assert (root / "hardware" / "firmware" / "esp32" / subdir).is_dir()

    # 5. Complete specification suite in docs/
    for doc in [
        "Operation Shadow — PRD v2.0.md",
        "Operation Shadow — TRD v2.0.md",
        "Operation Shadow — ULTRON Agent Architecture.md",
        "Operation Shadow — Backend & Frontend Architecture.md",
    ]:
        assert (root / "docs" / doc).is_file(), f"Expected document '{doc}' missing from docs/"
