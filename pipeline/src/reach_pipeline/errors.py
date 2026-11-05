"""Pipeline errors; each maps to one exit code (docs/implementation_plan.md, conventions)."""


class PipelineError(Exception):
    """Base class; `exit_code` is returned by the CLI."""

    exit_code = 1


class StageValidationError(PipelineError):
    """Inputs or results failed a validation check, or a previous manifest is missing/invalid."""

    exit_code = 1


class ConfigError(PipelineError):
    """The configuration file is missing or invalid."""

    exit_code = 2


class ExternalError(PipelineError):
    """Network, Valhalla or database failure after retries."""

    exit_code = 3


class BadRequestError(ExternalError):
    """Valhalla rejected the request (4xx), e.g. no route or no street near a location."""
