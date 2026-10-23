"""Production-hardening building blocks for the HTTP service (authentication, rate limiting, observability, tenancy).

Everything here is opt-in through environment variables (see docs/operations.md); with no configuration the server
behaves as it always has. The modules are framework-light so they can be unit tested without a running server.
"""
