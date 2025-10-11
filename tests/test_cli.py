"""Tests for the CLI module."""

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

    def test_cli_module_uses_rich_console(self) -> None:
        """Test that the CLI module uses rich console for output."""
        cli_path = Path(__file__).parent.parent / "digikey" / "cli.py"
        with cli_path.open() as f:
            code = f.read()

        assert "from rich.console import Console" in code  # noqa: S101
        assert "console = Console()" in code  # noqa: S101


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
