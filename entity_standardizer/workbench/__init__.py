"""Entity Standardizer Web Workbench, Multi-Format File I/O, Field Mapping & Matching Engine."""

from __future__ import annotations

from entity_standardizer.workbench.io_formats import (
    FileFormatSpec,
    SupportedFormat,
    detect_file_format,
    inspect_tabular_source,
    iter_tabular_rows,
    write_tabular_output,
    write_xlsx_sheets,
)
from entity_standardizer.workbench.mapping import (
    ColumnMapping,
    FieldRole,
    MappingConfig,
    PresetStore,
    auto_detect_mappings,
)
from entity_standardizer.workbench.match_runner import (
    ALL_MATCH_SIGNALS,
    DedupSession,
    MatchingOptions,
    MatchPairView,
    MatchSession,
    MemberRosterSource,
    load_member_roster_map,
    run_cross_system_match,
    run_single_file_dedup,
)
from entity_standardizer.workbench.options import StandardizationOptions
from entity_standardizer.workbench.standardize_runner import (
    preview_standardize_source,
    standardize_row_with_config,
    standardize_tabular_file,
)

__all__ = [
    "ALL_MATCH_SIGNALS",
    "ColumnMapping",
    "DedupSession",
    "FieldRole",
    "FileFormatSpec",
    "MappingConfig",
    "MatchPairView",
    "MatchSession",
    "MatchingOptions",
    "MemberRosterSource",
    "PresetStore",
    "StandardizationOptions",
    "SupportedFormat",
    "auto_detect_mappings",
    "detect_file_format",
    "inspect_tabular_source",
    "iter_tabular_rows",
    "load_member_roster_map",
    "preview_standardize_source",
    "run_cross_system_match",
    "run_single_file_dedup",
    "standardize_row_with_config",
    "standardize_tabular_file",
    "write_tabular_output",
    "write_xlsx_sheets",
]
