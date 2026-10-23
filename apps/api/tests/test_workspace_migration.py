import hashlib
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION_HASHES = {
    "0001_document_baseline.py": (
        "0f96887c990dac144c3614e6fa3588f7418b6ccc45abf7e068d90171f21471e9"
    ),
    "0002_investigation_foundation.py": (
        "8a8c7a80b3c7a9ed7a1d2acc8708ba46e016856945484dd00724ed9f2e6282a8"
    ),
    "0003_investigation_engine.py": (
        "f574bcfc6bb2aab6e49849f21c18c6f39a9999c5bbca69296470bd39b9e5cee9"
    ),
    "0004_workspace_isolation.py": (
        "fcc3d3a22e02cb66df2c49920478f4bc1d5a8e84957f2c764bb71d6e6113ca08"
    ),
    "0005_data_source_foundation.py": (
        "aa217dea2d127d86f919ede74a58c830bc75f677a54500e98558c613a8ac01d5"
    ),
}


def test_existing_migrations_are_byte_for_byte_unchanged() -> None:
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    actual = {
        name: hashlib.sha256((versions / name).read_bytes()).hexdigest()
        for name in MIGRATION_HASHES
    }
    assert actual == MIGRATION_HASHES


def test_source_import_migration_is_the_only_head() -> None:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0006_source_import_pipeline"]
    assert script.get_revision("0006_source_import_pipeline").down_revision == (
        "0005_data_source_foundation"
    )
    assert script.get_revision("0005_data_source_foundation").down_revision == (
        "0004_workspace_isolation"
    )
    assert script.get_revision("0004_workspace_isolation").down_revision == (
        "0003_investigation_engine"
    )
