"""Native, offline desktop interface for repository lineage scans."""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tkinter import (
    END,
    LEFT,
    TclError,
    StringVar,
    Text,
    Tk,
    Toplevel,
    filedialog,
    messagebox,
    ttk,
)
from typing import TypeVar

from lightweight_lineage.options import (
    ScanOptions,
    parse_mapping,
    parse_template_variable,
)
from lightweight_lineage.runner import ScanRunResult, run_scan

_T = TypeVar("_T")


class GuiUnavailableError(RuntimeError):
    """Raised when a desktop display cannot be opened."""


def _parse_lines(
    value: str,
    parser: Callable[[str], _T],
    label: str,
) -> tuple[_T, ...]:
    parsed: list[_T] = []
    for line_number, line in enumerate(value.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed.append(parser(line))
        except ValueError as error:
            raise ValueError(f"{label} line {line_number}: {error}") from error
    return tuple(parsed)


def build_scan_options(
    source_text: str,
    timeout_text: str,
    mapping_text: str,
    template_text: str,
    dialect_text: str = "tsql",
) -> ScanOptions:
    """Validate form values and create the same options used by the CLI."""
    source_value = source_text.strip()
    if not source_value:
        raise ValueError("Choose a source repository directory.")
    source = Path(source_value).expanduser()
    if not source.exists():
        raise ValueError(f"Source directory does not exist: {source}")
    if not source.is_dir():
        raise ValueError(f"Source is not a directory: {source}")
    if not os.access(source, os.R_OK):
        raise ValueError(f"Source directory is not readable: {source}")

    try:
        timeout = int(timeout_text)
    except ValueError as error:
        raise ValueError("Timeout must be a whole number of seconds.") from error
    if timeout < 1:
        raise ValueError("Timeout must be at least one second.")
    dialect = dialect_text.casefold()
    if dialect not in {"tsql", "redshift"}:
        raise ValueError("Choose either T-SQL or Redshift as the SQL dialect.")

    mappings = _parse_lines(mapping_text, parse_mapping, "Mapping")
    variables = _parse_lines(template_text, parse_template_variable, "Template variable")
    return ScanOptions(
        source=source,
        timeout_seconds=timeout,
        dialect=dialect,
        mappings=mappings,
        template_variables=variables,
    )


class _LineageGui:
    def __init__(self, root: Tk, source: Path | None) -> None:
        self.root = root
        self.root.title("Lightweight Lineage")
        self.root.geometry("900x700")
        self.root.minsize(720, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

        self._source = StringVar(value=str(source or ""))
        self._output = StringVar()
        self._format = StringVar(value="html")
        self._timeout = StringVar(value="300")
        self._dialect = StringVar(value="tsql")
        self._status = StringVar(value="Select a repository to begin.")
        self._last_result: ScanRunResult | None = None
        self._future: Future[ScanRunResult] | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="lineage-scan",
        )

        panel = ttk.Frame(root, padding=18)
        panel.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)

        ttk.Label(panel, text="Source repository").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Entry(panel, textvariable=self._source).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12)
        )
        ttk.Button(panel, text="Browse...", command=self._browse_source).grid(
            row=1, column=2, sticky="ew", padx=(8, 0), pady=(4, 12)
        )

        ttk.Label(panel, text="Output file (leave blank for default)").grid(
            row=2, column=0, columnspan=3, sticky="w"
        )
        ttk.Entry(panel, textvariable=self._output).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(4, 12)
        )
        ttk.Button(panel, text="Choose...", command=self._browse_output).grid(
            row=3, column=2, sticky="ew", padx=(8, 0), pady=(4, 12)
        )

        settings = ttk.Frame(panel)
        settings.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(2, weight=1)
        ttk.Label(settings, text="Report format").grid(row=0, column=0, sticky="w")
        ttk.Label(settings, text="Timeout (seconds)").grid(row=0, column=1, sticky="w")
        ttk.Label(settings, text="SQL dialect").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            settings,
            textvariable=self._format,
            values=("html", "json"),
            state="readonly",
            width=12,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(settings, textvariable=self._timeout, width=12).grid(
            row=1, column=1, sticky="w", pady=(4, 0)
        )
        ttk.Combobox(
            settings,
            textvariable=self._dialect,
            values=("tsql", "redshift"),
            state="readonly",
            width=12,
        ).grid(row=1, column=2, sticky="w", pady=(4, 0))

        ttk.Label(panel, text="Object mappings (one ALIAS=TARGET per line)").grid(
            row=5, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(panel, text="Template values (one NAME=VALUE per line)").grid(
            row=5, column=1, columnspan=2, sticky="w", pady=(0, 4), padx=(12, 0)
        )
        self._mappings = Text(panel, height=6, wrap="none", undo=True)
        self._mappings.grid(row=6, column=0, sticky="nsew")
        self._variables = Text(panel, height=6, wrap="none", undo=True)
        self._variables.grid(row=6, column=1, columnspan=2, sticky="nsew", padx=(12, 0))
        panel.rowconfigure(6, weight=1)

        ttk.Label(
            panel,
            text="The scan runs locally. SQL and template diagnostics are available separately after completion.",
            wraplength=840,
        ).grid(row=7, column=0, columnspan=3, sticky="w", pady=(10, 12))

        actions = ttk.Frame(panel)
        actions.grid(row=8, column=0, columnspan=3, sticky="ew")
        self._run_button = ttk.Button(
            actions,
            text="Generate lineage",
            command=self._start_scan,
        )
        self._run_button.pack(side=LEFT)
        self._open_button = ttk.Button(
            actions,
            text="Open HTML report",
            command=self._open_report,
            state="disabled",
        )
        self._open_button.pack(side=LEFT, padx=(8, 0))
        self._diagnostics_button = ttk.Button(
            actions,
            text="View diagnostics",
            command=self._show_diagnostics,
            state="disabled",
        )
        self._diagnostics_button.pack(side=LEFT, padx=(8, 0))

        ttk.Label(
            panel,
            textvariable=self._status,
            wraplength=850,
            justify=LEFT,
        ).grid(row=9, column=0, columnspan=3, sticky="ew", pady=(12, 0))

    def _browse_source(self) -> None:
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Choose a source repository",
            initialdir=self._source.get() or str(Path.cwd()),
        )
        if selected:
            self._source.set(selected)

    def _browse_output(self) -> None:
        output_format = self._format.get()
        extension = ".html" if output_format == "html" else ".json"
        source = self._source.get().strip()
        initial_directory = Path(source).expanduser() if source else Path.cwd()
        if not initial_directory.is_dir():
            initial_directory = Path.cwd()
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Choose lineage output",
            initialdir=str(initial_directory),
            initialfile=f"lineage{extension}",
            defaultextension=extension,
            filetypes=((f"{output_format.upper()} report", f"*{extension}"),),
        )
        if selected:
            self._output.set(selected)

    def _start_scan(self) -> None:
        if self._future is not None:
            return
        try:
            options = build_scan_options(
                self._source.get(),
                self._timeout.get(),
                self._mappings.get("1.0", "end-1c"),
                self._variables.get("1.0", "end-1c"),
                self._dialect.get(),
            )
        except ValueError as error:
            self._status.set(str(error))
            messagebox.showerror("Invalid scan options", str(error), parent=self.root)
            return

        output_text = self._output.get().strip()
        output = Path(output_text).expanduser() if output_text else None
        if output is not None and output.exists() and output.is_dir():
            messagebox.showerror(
                "Invalid output file",
                f"Output path is a directory: {output}",
                parent=self.root,
            )
            return
        output_format = self._format.get().casefold()
        if output_format not in {"json", "html"}:
            messagebox.showerror(
                "Invalid report format",
                "Choose either HTML or JSON.",
                parent=self.root,
            )
            return

        self._last_result = None
        self._open_button.configure(state="disabled")
        self._diagnostics_button.configure(state="disabled")
        self._run_button.configure(state="disabled")
        self._status.set("Scanning repository...")
        self._future = self._executor.submit(
            run_scan,
            options,
            output_format=output_format,
            output=output,
        )
        self.root.after(100, self._poll_scan)

    def _poll_scan(self) -> None:
        future = self._future
        if future is None:
            return
        if not future.done():
            self.root.after(100, self._poll_scan)
            return

        self._future = None
        self._run_button.configure(state="normal")
        error = future.exception()
        if error is not None:
            self._status.set(f"Scan failed: {error}")
            messagebox.showerror(
                "Lineage scan failed",
                f"{type(error).__name__}: {error}",
                parent=self.root,
            )
            return

        result = future.result()
        self._last_result = result
        diagnostics = result.graph["diagnostics"]
        self._status.set(
            f"Finished with {len(diagnostics)} diagnostic(s). "
            f"Report saved to {result.destination}"
        )
        self._diagnostics_button.configure(state="normal")
        if result.output_format == "html":
            self._open_button.configure(state="normal")

    def _open_report(self) -> None:
        result = self._last_result
        if result is None or result.output_format != "html":
            return
        if not webbrowser.open(result.destination.resolve().as_uri()):
            messagebox.showerror(
                "Unable to open report",
                f"Open this report manually:\n{result.destination}",
                parent=self.root,
            )

    def _show_diagnostics(self) -> None:
        result = self._last_result
        if result is None:
            return
        window = Toplevel(self.root)
        window.title("Lineage diagnostics")
        window.geometry("760x420")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        text = Text(window, wrap="word", padx=10, pady=10)
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        diagnostics = result.graph["diagnostics"]
        if not diagnostics:
            text.insert(END, "No warnings or errors were reported.")
        for diagnostic in diagnostics:
            location = diagnostic.get("file", "Unknown file")
            line = diagnostic.get("line")
            column = diagnostic.get("column")
            if line:
                location += f":{line}"
                if column:
                    location += f":{column}"
            text.insert(
                END,
                f"[{diagnostic.get('severity', 'info').upper()}] "
                f"{diagnostic.get('code', 'diagnostic')}\n"
                f"{location}\n{diagnostic.get('message', '')}\n\n",
            )
        text.configure(state="disabled")

    def _close(self) -> None:
        if self._future is not None and not self._future.done():
            messagebox.showinfo(
                "Scan in progress",
                "Wait for the current scan to finish before closing.",
                parent=self.root,
            )
            return
        self._executor.shutdown(wait=True, cancel_futures=True)
        self.root.destroy()


def launch_gui(source: Path | None = None) -> None:
    """Open the desktop GUI and block until its window is closed."""
    try:
        root = Tk()
    except TclError as error:
        raise GuiUnavailableError(
            "Unable to open the desktop interface. Confirm that a graphical desktop is available."
        ) from error
    _LineageGui(root, source)
    root.mainloop()


__all__ = ["GuiUnavailableError", "build_scan_options", "launch_gui"]
