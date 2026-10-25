#!/usr/bin/env python3
"""
Example script demonstrating the Digi-Key API CLI usage in Python scripts.

This script shows how to programmatically interact with the CLI or use
the underlying API directly.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def check_credentials() -> bool:
    """Check if credentials are configured."""
    return bool(
        os.getenv("DIGIKEY_CLIENT_ID")
        and os.getenv("DIGIKEY_CLIENT_SECRET")
        and os.getenv("DIGIKEY_STORAGE_PATH")
    )


def load_env_file() -> None:
    """Load credentials from ~/.digikey/.env file."""
    env_file = Path.home() / ".digikey" / ".env"
    if env_file.exists():
        with env_file.open() as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value
        print(f"✓ Loaded credentials from {env_file}")
    else:
        print(f"✗ No credentials file found at {env_file}")
        print("  Run 'digikey auth' to configure credentials")
        sys.exit(1)


def run_cli_command(command: list[str]) -> dict:
    """Run a CLI command and return JSON output."""
    try:
        result = subprocess.run(
            ["digikey", *command, "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        sys.exit(1)


def example_search() -> None:
    """Example: Search for parts."""
    print("\n=== Example 1: Search for resistors ===")

    # Method 1: Using CLI via subprocess
    print("\nMethod 1: Using CLI")
    result = run_cli_command(["search", "resistor 10k", "--limit", "5"])
    if result.get("products"):
        print(f"Found {len(result['products'])} products")
        for product in result["products"][:3]:
            desc = product.get("product_description", "N/A")[:60]
            print(f"  - {product.get('digi_key_part_number')}: {desc}")

    # Method 2: Using Python API directly
    print("\nMethod 2: Using Python API")
    try:
        import digikey
        from digikey.v4.productinformation import KeywordRequest

        digikey.use_local_tool()
        search_request = KeywordRequest(keywords="resistor 10k", record_count=5)
        result = digikey.keyword_search(body=search_request)

        if result and hasattr(result, "products_count"):
            print(f"Found {result.products_count} products")
            if hasattr(result, "products"):
                for product in result.products[:3]:
                    desc = (
                        product.product_description[:60]
                        if hasattr(product, "product_description")
                        else "N/A"
                    )
                    print(f"  - {product.digi_key_part_number}: {desc}")
    except ImportError:
        print("  (Python API not available - install digikey-api package)")
    except Exception as e:  # noqa: BLE001
        print(f"  Error: {e}")


def example_product_details() -> None:
    """Example: Get product details."""
    print("\n=== Example 2: Get product details ===")

    part_number = "296-6501-1-ND"
    print(f"\nGetting details for: {part_number}")

    # Using CLI
    result = run_cli_command(["product-details", part_number])
    print(f"Part Number: {result.get('digi_key_part_number')}")
    print(f"Manufacturer: {result.get('manufacturer', {}).get('value', 'N/A')}")
    print(f"Description: {result.get('product_description', 'N/A')}")
    print(f"Stock: {result.get('quantity_available', 'N/A')}")
    if "unit_price" in result:
        print(f"Price: ${result['unit_price']}")


def main() -> None:
    """Main function."""
    print("Digi-Key API CLI - Example Script")
    print("=" * 50)

    # Load credentials
    if not check_credentials():
        print("\nLoading credentials from ~/.digikey/.env...")
        load_env_file()

    if not check_credentials():
        print("\n✗ Credentials not configured")
        print("  Please run 'digikey auth' to configure")
        sys.exit(1)

    print("\n✓ Credentials configured")

    # Run examples
    try:
        example_search()
        example_product_details()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)

    print("\n" + "=" * 50)
    print("Examples completed!")


if __name__ == "__main__":
    main()
