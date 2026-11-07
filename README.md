# Lightweight Lineage

An offline tool for scanning repositories and generating data lineage.

## Development setup

Requires Python 3.12 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## Tests

Run the unit tests and Python syntax check with:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

Continuous integration is configured to run these checks on Windows and macOS
with Python 3.12.

## Current command

The current command parses T-SQL files and emits object-level lineage as
deterministic JSON or a self-contained interactive HTML report. The HTML
report works offline, with clickable upstream/downstream highlighting and a
separate diagnostics panel.

```powershell
lineage scan path\to\repository --format html
lineage scan path\to\repository
```

The output format defaults to `json`; `--format html` selects the interactive
report. When `--output` is omitted, the selected format is saved beside the
source directory in an `outputs` folder as `lineage.json` or `lineage.html`.
The folder is created if needed. Use `--output FILE` to choose another path.

The command defaults to a five-minute whole-scan timeout. `--timeout` overrides
it in seconds. Repeated `--map ALIAS=TARGET` options supply explicit object
mappings. Repeated `--var NAME=VALUE` options supply Jinja2 template values;
the built-in `ref()` and `source()` helpers support common SQL template
references. Undefined variables and unsupported macros are reported as
template errors. The CLI prints the path where it saved the report.

The current T-SQL extractor handles permanent table/view/procedure objects,
CTEs and nested queries, common static DML, synonyms, statically named
procedure calls within procedure bodies, linked-server four-part names,
`BULK INSERT`, and `OPENROWSET(BULK ...)`.
Non-BULK `OPENROWSET` connection strings are not interpreted. SQL diagnostics
report parsing failures, not SQL Server semantic or execution errors.