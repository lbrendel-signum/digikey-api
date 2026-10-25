# GitHub Copilot Instructions for digikey-api

## Project Overview

`digikey-api` is a Python client library for the Digi-Key Part Search API. It provides a clean, Pythonic interface to interact with Digi-Key's API services for searching electronic components, retrieving product details, and managing orders.

## Project Structure

### Core Directories

- **`digikey/`** - Main package directory
  - **`v3/`** - API v3 client implementations (generated from Swagger)
    - `productinformation/` - Product search and details
    - `ordersupport/` - Order history and status
    - `batchproductdetails/` - Batch product queries
  - **`v4/`** - API v4 client implementations (current/recommended)
    - `productinformation/` - Product search and details
    - `ordersupport/` - Order history and status
    - `batchproductdetails/` - Batch product queries
  - **`oauth/`** - OAuth2 authentication handling
  - `constants.py` - Configuration constants
  - `decorators.py` - Utility decorators
  - `exceptions.py` - Custom exceptions
  - `utils.py` - Utility functions

- **`generate-v3-api/`** - Scripts for auto-generating API v3 clients from Swagger specifications
  - `generage_client_swagger.py` - Main code generation script using Swagger Codegen

- **`tests/`** - Test suite
  - Unit tests for API functionality
  - Mock responses for testing without API calls

- **`docs/`** - Documentation files

## Key Technologies

- **Python 3.10+** (supports up to 3.12)
- **OAuth2** for authentication with Digi-Key API
- **Swagger Codegen** for generating API clients (v3)
- **Ruff** for linting and code formatting
- **pytest** for testing
- **uv** for dependency management

## Coding Standards

### Python Version
- Target Python 3.10+ (specified in pyproject.toml)
- Avoid Python 3.13+ features

### Linting and Formatting
- Use **Ruff** for linting and formatting
- Line length: 100 characters
- Configuration in `pyproject.toml` under `[tool.ruff]`
- Many rules are enabled with specific ignores (see pyproject.toml)

### Type Hints
- Use type hints where appropriate
- Return type hints (e.g., `-> None`, `-> str`) are preferred
- Use `from __future__ import annotations` for forward references if needed

### Docstrings
- Include docstrings for public functions and classes
- Follow existing patterns in the codebase
- Auto-generated code (from Swagger) includes detailed docstrings

### Imports
- Standard library imports first
- Third-party imports second
- Local imports last
- Use absolute imports for the `digikey` package

### Error Handling
- Use custom exceptions from `digikey.exceptions` where appropriate
- Handle API errors gracefully
- Include informative error messages

## API Client Design

### Authentication
- All API calls require OAuth2 authentication
- Tokens are cached in the directory specified by `DIGIKEY_STORAGE_PATH`
- The library handles token refresh automatically
- Default grant is the browser authorization-code flow. OAuth callback URL: `https://localhost:8139/digikey_callback`
- Local tools skip the browser. Call `digikey.use_local_tool()` or set `DIGIKEY_LOCAL_TOOL=1` / `DIGIKEY_NO_BROWSER=1` to use the client-credentials grant. The CLI always does this. Parallel token requests share a file lock.

### Environment Variables
- `DIGIKEY_CLIENT_ID` - API client ID
- `DIGIKEY_CLIENT_SECRET` - API client secret
- `DIGIKEY_CLIENT_SANDBOX` - Use sandbox API (True/False)
- `DIGIKEY_STORAGE_PATH` - Directory for token cache
- `DIGIKEY_LOCAL_TOOL` / `DIGIKEY_NO_BROWSER` - Skip browser verification and use client credentials

### API Versions
- **V4** is the current and recommended version
- **V3** is maintained for backward compatibility
- When adding features, prioritize V4 unless V3-specific work is required

### Generated Code
- Much of the v3 and v4 client code is auto-generated from Swagger specifications
- Do not manually edit files with "auto generated" comments unless absolutely necessary
- Modifications to generated code may be lost on regeneration
- If changes are needed, consider updating the generation script or Swagger spec instead

## Testing

### Running Tests
```bash
pytest
pytest --cov  # With coverage
```

### Test Structure
- Tests use `pytest` framework
- Mock API responses using `responses` library
- Utilities in `tests/utils.py` provide helpers for mocking Digi-Key API calls
- Use `digikey_api_mock_response()` for API mocks
- Use `digikey_sso_mock_response()` for SSO mocks

### Test Files
- Keep tests in `tests/` directory
- Mirror the package structure where appropriate
- Use descriptive test names: `test_<functionality>_<scenario>`

## Common Patterns

### API Client Usage
```python
import os
from pathlib import Path
import digikey
from digikey.v4.productinformation import KeywordRequest

# Setup environment
os.environ['DIGIKEY_CLIENT_ID'] = 'client_id'
os.environ['DIGIKEY_CLIENT_SECRET'] = 'client_secret'
os.environ['DIGIKEY_STORAGE_PATH'] = 'path/to/cache'

# Make API calls
part = digikey.product_details('296-6501-1-ND')
```

### Rate Limiting
- The API has rate limits
- Pass `api_limits={}` dict to get limit information
- Values populated with: `api_requests_limit`, `api_requests_remaining`

### Pagination
- Maximum 50 results per request
- Use `offset` parameter for pagination
- Example: `offset=0` for first page, `offset=50` for second page

## Development Guidelines

### Making Changes

1. **For API Updates**
   - If updating V3 clients, use the Swagger Codegen script in `generate-v3-api/`
   - If updating V4, consider if changes should be made to generated code or custom wrappers

2. **For New Features**
   - Add to the appropriate version (prefer V4)
   - Update top-level exports in `digikey/__init__.py` if needed
   - Add tests
   - Update README.md if adding user-facing functionality

3. **For Bug Fixes**
   - Add a test that reproduces the bug
   - Fix the issue
   - Ensure all tests pass

### Code Generation (V3)
- The `generage_client_swagger.py` script automates client generation
- It downloads Swagger specs from Digi-Key API
- Uses Swagger Codegen CLI (Java-based) to generate Python clients
- Customize generation through config dictionaries in the script

### Pull Requests
- Ensure all tests pass
- Run linting with Ruff
- Update documentation if needed
- Keep changes focused and minimal

## Dependencies

### Production
- `requests` - HTTP client
- `certauth`, `certifi` - Certificate handling
- `inflection` - String transformations
- `retrying` - Retry logic
- `six`, `urllib3` - Compatibility and utilities

### Development
- `pytest`, `pytest-cov` - Testing
- `coverage` - Test coverage
- `flake8`, `ruff` - Linting
- `mock`, `responses` - Testing utilities
- `gitpython` - For code generation scripts

## Additional Notes

### License
- GNU General Public License v3.0 (GPL-3.0)
- See LICENSE file for full text

### Community Project
- This is a community-maintained project
- Not officially maintained by Digi-Key
- Contributions are welcome

### API Documentation
- Official Digi-Key API docs: https://developer.digikey.com/
- Register for API access: https://developer.digikey.com/get_started
- API endpoints documentation available at the developer portal

## Common Tasks

### Adding a New API Endpoint (V4)
1. Check if the endpoint is available in Digi-Key's API
2. Add the implementation in the appropriate module under `digikey/v4/`
3. Add a wrapper function in `digikey/v4/api.py`
4. Export it from `digikey/__init__.py`
5. Add tests in `tests/`
6. Update README.md with usage example

### Debugging OAuth Issues
- Delete the token cache directory and re-authenticate
- Verify client ID and secret
- Check OAuth callback URL configuration
- Ensure not using sandbox credentials in production

### Handling API Changes
- Monitor Digi-Key's API changelog
- Update Swagger specs if available
- Regenerate clients if using V3
- Update models and types as needed
- Maintain backward compatibility where possible
