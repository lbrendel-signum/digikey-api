# Digi-Key API CLI Usage Guide

The `digikey-api` package includes a command-line interface (CLI) that provides easy access to the Digi-Key API from your terminal.

## Installation

First, install the package:

```bash
pip install digikey-api
```

## Quick Start

### 1. Authentication

Before using the CLI, you need to authenticate with your Digi-Key API credentials:

```bash
digikey auth
```

This command will:
- Prompt you for your Client ID and Client Secret
- Request an access token with those keys (no browser window)
- Save your credentials to `~/.digikey/.env` for future use
- Store the OAuth token in `~/.digikey/token_storage.json`

The CLI is a local tool. `search` and `product-details` load `~/.digikey/.env` themselves and reuse
one token across parallel processes. They do not open a Digi-Key login.

You can also provide credentials directly:

```bash
digikey auth --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
```

For sandbox testing:

```bash
digikey auth --sandbox
```

To use a custom storage path:

```bash
digikey auth --storage-path /path/to/storage
```

### 2. Using Saved Credentials

CLI commands load `~/.digikey/.env` automatically. To put the same values in your shell:

```bash
export $(cat ~/.digikey/.env | xargs)
```

Or add this to your `.bashrc` or `.zshrc`:

```bash
if [ -f ~/.digikey/.env ]; then
    export $(cat ~/.digikey/.env | xargs)
fi
```

## Commands

### Search for Parts

Search for electronic components using keywords:

```bash
# Basic search
digikey search "resistor 10k"

# Limit number of results
digikey search "capacitor 0805" --limit 20

# Enable verbose logging
digikey search "led red" --verbose

# Get raw JSON output
digikey search "transistor" --json
```

**Output:**
- Part Number
- Manufacturer
- Description (truncated to 60 characters)
- Stock availability

### Get Product Details

Retrieve detailed information about a specific part using its Digi-Key part number:

```bash
# Get product details
digikey product-details 296-6501-1-ND

# Get JSON output
digikey product-details 296-6501-1-ND --json

# Enable verbose logging
digikey product-details 296-6501-1-ND --verbose
```

**Output:**
- Digi-Key Part Number
- Manufacturer Part Number
- Manufacturer
- Description
- Detailed Description
- Quantity Available
- Unit Price

### Version Information

Display version information:

```bash
digikey version
```

## Options

### Global Options

All commands support these options:

- `--verbose, -v`: Enable verbose logging (shows debug information)
- `--help`: Show help message for the command

### Command-Specific Options

#### `auth` command

- `--client-id, -i`: Your Digi-Key API Client ID (will prompt if not provided)
- `--client-secret, -s`: Your Digi-Key API Client Secret (will prompt if not provided)
- `--sandbox`: Use the sandbox API instead of production
- `--storage-path, -p`: Path to store authentication tokens (default: ~/.digikey)

#### `search` command

- `--limit, -l`: Maximum number of results to return (default: 10)
- `--json, -j`: Output raw JSON instead of formatted table

#### `product-details` command

- `--json, -j`: Output raw JSON instead of formatted table

## Examples

### Complete Workflow

```bash
# 1. Authenticate once
digikey auth

# 2. Search for a part
digikey search "arduino uno"

# 3. Get details for a specific part
digikey product-details 1050-1024-ND

# 4. Get JSON data for integration with other tools
digikey product-details 1050-1024-ND --json | jq '.unit_price'
```

### Using with Scripts

```bash
#!/bin/bash
# search_and_get_price.sh

# Export credentials
export $(cat ~/.digikey/.env | xargs)

# Search for a part and get the first result
PART_NUMBER=$(digikey search "$1" --json | jq -r '.products[0].digi_key_part_number')

# Get detailed pricing
digikey product-details "$PART_NUMBER" --json | jq '.unit_price'
```

Usage:
```bash
./search_and_get_price.sh "resistor 10k 0805"
```

## Troubleshooting

### "API credentials not configured"

The command stops before calling the API when the client id and secret are missing, so it does not
open a login. Either:
1. Run `digikey auth` to save credentials
2. Set environment variables manually:
   ```bash
   export DIGIKEY_CLIENT_ID="your_client_id"
   export DIGIKEY_CLIENT_SECRET="your_client_secret"
   export DIGIKEY_STORAGE_PATH="$HOME/.digikey"
   ```

### "Module not found" errors

Make sure you have all dependencies installed:
```bash
pip install digikey-api[dev]
```

### OAuth authentication fails

`digikey auth` requests a token with the client id and secret and does not open a browser. If that
request fails, check that the application is registered and subscribed to the API product you are
calling.

Library code that still uses the browser flow needs the OAuth callback set to
`https://localhost:8139/digikey_callback`, and port 8139 has to be free. To force that same browser
flow off:

```bash
export DIGIKEY_LOCAL_TOOL=1
```

To drop a cached token and request a new one:

```bash
rm ~/.digikey/token_storage.json
digikey auth
```

### Sandbox vs Production

- Sandbox API is for testing and may return incomplete or dummy data
- Production API requires a production app registered on Digi-Key's developer portal
- Always use production credentials for real data

## API Documentation

For more information about the Digi-Key API:
- [Digi-Key API Portal](https://developer.digikey.com/)
- [Getting Started](https://developer.digikey.com/get_started)
- [API Documentation](https://developer.digikey.com/products)
