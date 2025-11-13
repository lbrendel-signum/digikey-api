"""Digikey API custom exceptions."""


class DigikeyError(Exception):
    """
    Base exception class for all Digikey API related errors.

    This exception serves as the parent class for all custom exceptions
    that may be raised when interacting with the Digikey API. It allows
    for catching all Digikey-specific errors with a single except clause.

    Raises:
        DigikeyError: Base exception for Digikey API operations.

    Example:
        try:
            # Digikey API operations
        except DigikeyError as e:
            print(f"Digikey API error occurred: {e}")

    """


class DigikeyTypeError(Exception):
    """
    Custom exception raised when there is a type-related error in Digikey API operations.

    This exception is typically raised when:
    - Invalid data types are passed to Digikey API functions
    - Type conversion fails during API response processing
    - Expected object types don't match actual types in API interactions

    Inherits from the base Exception class.
    """


class DigikeyOauthError(Exception):
    """
    Exception raised for OAuth-related errors when interacting with the Digikey API.

    This exception is typically raised when there are issues with:
    - OAuth token acquisition or refresh
    - Invalid or expired access tokens
    - Authentication failures during API requests
    - OAuth configuration problems

    Attributes:
        message (str): Explanation of the OAuth error that occurred

    """
