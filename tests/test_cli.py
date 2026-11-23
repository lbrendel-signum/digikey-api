"""Tests for the CLI module."""

import os
import tempfile
from pathlib import Path
from unittest import TestCase

import pytest

# We can't import the actual CLI because it requires dependencies
# So let's just test that the file is valid Python and has the right structure


class TestCLIStructure(TestCase):
    """Test CLI module structure."""

    def test_cli_module_exists(self) -> None:
        """Test that the CLI module file exists."""
        cli_path = Path(__file__).parent.parent / "digikey" / "cli.py"
        assert cli_path.exists()  # noqa: S101

    def test_cli_module_is_valid_python(self) -> None:
        """Test that the CLI module is valid Python."""
        cli_path = Path(__file__).parent.parent / "digikey" / "cli.py"
        with cli_path.open() as f:
            code = f.read()
        # This will raise SyntaxError if invalid
        compile(code, str(cli_path), "exec")

    def test_cli_module_has_required_commands(self) -> None:
        """Test that the CLI module has the required commands."""
        cli_path = Path(__file__).parent.parent / "digikey" / "cli.py"
        with cli_path.open() as f:
            code = f.read()

        # Check for required commands
        assert "def auth(" in code  # noqa: S101
        assert "def product_details(" in code  # noqa: S101
        assert "def search(" in code  # noqa: S101
        assert "def version(" in code  # noqa: S101

    def test_cli_module_imports_typer(self) -> None:
        """Test that the CLI module imports typer."""
        cli_path = Path(__file__).parent.parent / "digikey" / "cli.py"
        with cli_path.open() as f:
            code = f.read()

        assert "import typer" in code  # noqa: S101
        assert "typer.Typer" in code  # noqa: S101
        assert "prepare_local_session" in code  # noqa: S101
        assert "interactive=False" in code  # noqa: S101
        assert "A browser window will open" not in code  # noqa: S101

    def test_cli_module_uses_rich_console(self) -> None:
        """Test that the CLI module uses rich console for output."""
        cli_path = Path(__file__).parent.parent / "digikey" / "cli.py"
        with cli_path.open() as f:
            code = f.read()

        assert "from rich.console import Console" in code  # noqa: S101
        assert "console = Console()" in code  # noqa: S101

    def test_saved_credentials_enable_local_tool_mode(self) -> None:
        """CLI loads saved keys and skips browser verification."""
        from digikey import cli  # noqa: PLC0415

        keys = (
            "DIGIKEY_CLIENT_ID",
            "DIGIKEY_CLIENT_SECRET",
            "DIGIKEY_STORAGE_PATH",
            "DIGIKEY_LOCAL_TOOL",
        )
        saved = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            with tempfile.TemporaryDirectory() as storage:
                env_file = Path(storage) / ".env"
                env_file.write_text(
                    "DIGIKEY_CLIENT_ID=from-file\n"
                    "DIGIKEY_CLIENT_SECRET=secret-file\n"
                    f"DIGIKEY_STORAGE_PATH={storage}\n"
                    "UNRELATED_PATH=/should-not-load\n"
                    'export DIGIKEY_CLIENT_SANDBOX="True"\n'
                )
                cli.prepare_local_session(Path(storage))
                assert os.environ["DIGIKEY_CLIENT_ID"] == "from-file"  # noqa: S101
                assert os.environ["DIGIKEY_CLIENT_SECRET"] == "secret-file"  # noqa: S101
                assert os.environ["DIGIKEY_CLIENT_SANDBOX"] == "True"  # noqa: S101
                assert os.environ["DIGIKEY_LOCAL_TOOL"] == "1"  # noqa: S101
                assert os.environ.get("UNRELATED_PATH") is None  # noqa: S101
                assert cli.ensure_credentials() is True  # noqa: S101
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_missing_keys_stop_before_any_login(self) -> None:
        """A local command exits when the keys are missing."""
        from digikey import cli  # noqa: PLC0415

        keys = ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET", "DIGIKEY_LOCAL_TOOL")
        saved = {key: os.environ.get(key) for key in keys}
        try:
            for key in keys:
                os.environ.pop(key, None)
            with tempfile.TemporaryDirectory() as storage:
                cli.prepare_local_session(Path(storage))
                assert cli.ensure_credentials() is False  # noqa: S101
                assert os.environ["DIGIKEY_LOCAL_TOOL"] == "1"  # noqa: S101
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
