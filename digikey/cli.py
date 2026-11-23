"""CLI interface for the Digikey API using Typer."""

import json
import logging
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

import digikey
from digikey.v4.productinformation import KeywordRequest

app = typer.Typer(
    name="digikey",
    help=(
        "CLI interface for Digi-Key API - "
        "Search for electronic components and retrieve product details"
    ),
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)

# Default storage path for authentication tokens
DEFAULT_STORAGE_PATH = Path.home() / ".digikey"


def setup_logging(*, verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def ensure_storage_path() -> Path:
    """Ensure the storage path exists and return it."""
    storage_path = Path(os.getenv("DIGIKEY_STORAGE_PATH", DEFAULT_STORAGE_PATH))
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def load_saved_credentials(storage_path: Path | None = None) -> None:
    """
    Load Digi-Key keys saved by ``digikey auth`` into the environment.

    Values already set in the environment are left unchanged. The CLI reads
    these keys before it calls the API so a missing token is not treated as a
    signal to open a browser.
    """
    path = storage_path or Path(os.getenv("DIGIKEY_STORAGE_PATH", DEFAULT_STORAGE_PATH))
    env_file = path / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if not key.startswith("DIGIKEY_"):
            continue
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def prepare_local_session(storage_path: Path | None = None) -> None:
    """
    Use saved keys and skip browser verification.

    The CLI is a local tool. It has to know the client id and secret up front,
    and it must not start a browser login for every process.
    """
    load_saved_credentials(storage_path)
    digikey.use_local_tool()


def ensure_credentials() -> bool:
    """
    Check if credentials are configured.

    Returns True if credentials are set, False otherwise.
    """
    client_id = os.getenv("DIGIKEY_CLIENT_ID")
    client_secret = os.getenv("DIGIKEY_CLIENT_SECRET")

    if not client_id or not client_secret:
        err_console.print(
            "[red]Error:[/red] API credentials not configured. "
            "Please run [bold]digikey auth[/bold] first.",
        )
        return False
    return True


@app.command()
def auth(
    client_id: str = typer.Option(
        ...,
        "--client-id",
        "-i",
        help="Digi-Key API Client ID",
        prompt="Enter your Digi-Key API Client ID",
    ),
    client_secret: str = typer.Option(
        ...,
        "--client-secret",
        "-s",
        help="Digi-Key API Client Secret",
        prompt="Enter your Digi-Key API Client Secret",
        hide_input=True,
    ),
    sandbox: bool = typer.Option(
        False,
        "--sandbox",
        help="Use sandbox API (for testing)",
    ),
    storage_path: str | None = typer.Option(
        None,
        "--storage-path",
        "-p",
        help="Path to store authentication tokens (default: ~/.digikey)",
    ),
) -> None:
    """
    Save API credentials and request an access token.

    The token is requested with the client id and secret. A browser login is
    not opened. Credentials are written to a .env file for later commands.
    """
    # Set storage path
    final_storage_path = Path(storage_path) if storage_path else DEFAULT_STORAGE_PATH

    final_storage_path.mkdir(parents=True, exist_ok=True)

    # Save credentials to .env file
    env_file = final_storage_path / ".env"
    with env_file.open("w") as f:
        f.write(f"DIGIKEY_CLIENT_ID={client_id}\n")
        f.write(f"DIGIKEY_CLIENT_SECRET={client_secret}\n")
        f.write(f"DIGIKEY_STORAGE_PATH={final_storage_path}\n")
        if sandbox:
            f.write("DIGIKEY_CLIENT_SANDBOX=True\n")

    # Set environment variables for current session
    os.environ["DIGIKEY_CLIENT_ID"] = client_id
    os.environ["DIGIKEY_CLIENT_SECRET"] = client_secret
    os.environ["DIGIKEY_STORAGE_PATH"] = str(final_storage_path)
    if sandbox:
        os.environ["DIGIKEY_CLIENT_SANDBOX"] = "True"
    else:
        os.environ.pop("DIGIKEY_CLIENT_SANDBOX", None)
    prepare_local_session(final_storage_path)

    console.print(f"[green]✓[/green] Credentials saved to {env_file}")
    console.print(
        "\n[bold]Later commands read this file automatically.[/bold]\n"
        "You can also load it yourself with:\n"
        f"  export $(cat {env_file} | xargs)"
    )

    console.print(
        "\n[bold]Requesting an access token with your client id and secret.[/bold]"
    )
    console.print("Browser verification is not required.")

    try:
        from digikey.oauth.oauth2 import TokenHandler  # noqa: PLC0415

        token_handler = TokenHandler(version=4, sandbox=sandbox, interactive=False)
        token = token_handler.get_access_token()
        console.print(
            f"\n[green]✓[/green] Authentication successful! "
            f"Token expires: {token.expires}"
        )
        console.print("\n[bold]You can now use the API commands.[/bold]")
    except Exception as e:
        err_console.print(f"\n[red]Error during authentication:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def product_details(  # noqa: C901, PLR0912
    part_number: str = typer.Argument(..., help="Digi-Key part number to look up"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON"),
) -> None:
    """
    Retrieve detailed information for a specific Digi-Key part number.

    Example:
        digikey product-details 296-6501-1-ND

    """
    setup_logging(verbose=verbose)
    prepare_local_session()

    if not ensure_credentials():
        raise typer.Exit(1)

    try:
        console.print(f"Fetching product details for: [bold]{part_number}[/bold]")
        product = digikey.product_details(part_number)

        if json_output:
            # Output raw JSON
            if hasattr(product, "to_dict"):
                console.print_json(json.dumps(product.to_dict()))
            else:
                console.print_json(json.dumps(str(product)))
        # Pretty output
        elif product:
            table = Table(title=f"Product Details: {part_number}")
            table.add_column("Property", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")

            # Add key product information
            if hasattr(product, "digi_key_part_number"):
                table.add_row("Digi-Key Part Number", str(product.digi_key_part_number))
            if hasattr(product, "manufacturer_part_number"):
                table.add_row("Manufacturer Part Number", str(product.manufacturer_part_number))
            if hasattr(product, "manufacturer") and hasattr(product.manufacturer, "value"):
                table.add_row("Manufacturer", str(product.manufacturer.value))
            if hasattr(product, "product_description"):
                table.add_row("Description", str(product.product_description))
            if hasattr(product, "detailed_description"):
                table.add_row("Detailed Description", str(product.detailed_description))
            if hasattr(product, "quantity_available"):
                table.add_row("Quantity Available", str(product.quantity_available))
            if hasattr(product, "unit_price"):
                table.add_row("Unit Price", f"${product.unit_price}")

            console.print(table)
        else:
            console.print(f"[yellow]No product found for part number: {part_number}[/yellow]")

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if verbose:
            raise
        raise typer.Exit(1) from e


@app.command()
def search(  # noqa: C901
    keywords: str = typer.Argument(..., help="Search keywords"),
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum number of results to return"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output raw JSON"),
) -> None:
    """
    Search for products using keywords.

    Example:
        digikey search "resistor 10k"
        digikey search "capacitor" --limit 20

    """
    setup_logging(verbose=verbose)
    prepare_local_session()

    if not ensure_credentials():
        raise typer.Exit(1)

    try:
        console.print(f"Searching for: [bold]{keywords}[/bold]")

        # Create search request
        search_request = KeywordRequest(
            keywords=keywords,
            record_count=limit,
        )

        results = digikey.keyword_search(body=search_request)

        if json_output:
            # Output raw JSON
            if hasattr(results, "to_dict"):
                console.print_json(json.dumps(results.to_dict()))
            else:
                console.print_json(json.dumps(str(results)))
        # Pretty output
        elif results and hasattr(results, "products_count") and results.products_count > 0:
            console.print(f"\n[green]Found {results.products_count} results[/green]")

            if hasattr(results, "products") and results.products:
                table = Table(title="Search Results")
                table.add_column("Part Number", style="cyan", no_wrap=True)
                table.add_column("Manufacturer", style="blue")
                table.add_column("Description", style="white")
                table.add_column("Stock", style="green")

                max_desc_length = 60
                for product in results.products[:limit]:
                    part_num = (
                        str(product.digi_key_part_number)
                        if hasattr(product, "digi_key_part_number")
                        else "N/A"
                    )
                    mfr = "N/A"
                    if hasattr(product, "manufacturer") and hasattr(
                        product.manufacturer, "value"
                    ):
                        mfr = str(product.manufacturer.value)
                    desc = (
                        str(product.product_description)
                        if hasattr(product, "product_description")
                        else "N/A"
                    )
                    stock = (
                        str(product.quantity_available)
                        if hasattr(product, "quantity_available")
                        else "N/A"
                    )

                    # Truncate description if too long
                    if len(desc) > max_desc_length:
                        desc = desc[:57] + "..."

                    table.add_row(part_num, mfr, desc, stock)

                console.print(table)
        else:
            console.print(f"[yellow]No results found for: {keywords}[/yellow]")

    except Exception as e:
        err_console.print(f"[red]Error:[/red] {e}")
        if verbose:
            raise
        raise typer.Exit(1) from e


@app.command()
def version() -> None:
    """Display version information."""
    console.print("[bold]Digi-Key API CLI[/bold]")
    console.print("Package: digikey-api")
    console.print("\nFor more information, visit: https://github.com/peeter123/digikey-api")


if __name__ == "__main__":
    app()
