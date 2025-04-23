import typer
import re
import json
import calendar
import ollama
import inquirer  # For interactive prompts
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from collections import defaultdict

# --- Configuration Management ---

APP_NAME = "wdid"
CONFIG_DIR = Path(typer.get_app_dir(APP_NAME))
CONFIG_FILE = CONFIG_DIR / "config.json"


def ensure_config_dir_exists():
    """Creates the config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """Loads configuration from the JSON file."""
    ensure_config_dir_exists()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            typer.echo(
                f"Warning: Configuration file {CONFIG_FILE} is corrupted. Starting fresh.",
                err=True,
            )
            return {}
    return {}


def save_config(config: Dict[str, Any]):
    """Saves configuration to the JSON file."""
    ensure_config_dir_exists()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


def get_notes_path() -> Optional[Path]:
    """Gets the notes path from config."""
    config = load_config()
    path_str = config.get("notes_path")
    if path_str:
        path = Path(path_str)
        if path.is_dir():
            return path
        else:
            typer.echo(
                f"Warning: Configured notes path '{path_str}' is not a valid directory.",
                err=True,
            )
            return None
    return None


# --- Core File Parsing and Finding Logic ---


def parse_fname(fname: str) -> Optional[datetime]:
    """Parses filenames like '11th-apr-2025.md' into datetime objects."""
    # Match variations like 1st, 2nd, 3rd, 4th...
    m = re.match(r"(\d+)(?:st|nd|rd|th)-([a-z]{3})-(\d{4})\.md$", fname, re.IGNORECASE)
    if not m:
        return None
    day, mon, year = m.groups()
    try:
        return datetime.strptime(f"{day}-{mon}-{year}", "%d-%b-%Y")
    except ValueError:
        typer.echo(f"Warning: Could not parse date from filename: {fname}", err=True)
        return None


def find_notes_in_range(
    notes_dir: Path, start_dt: datetime, end_dt: datetime
) -> List[Tuple[datetime, Path]]:
    """Finds note files within a specific date range."""
    files_to_process = []
    if not notes_dir or not notes_dir.is_dir():
        typer.echo(
            f"Error: Notes directory '{notes_dir}' not found or invalid.", err=True
        )
        raise typer.Exit(code=1)

    typer.echo(f"Scanning for notes in: {notes_dir}")
    for p in notes_dir.glob("*.md"):
        file_dt = parse_fname(p.name)
        if file_dt:
            # Ensure file_dt is timezone-naive for comparison if start/end are
            file_dt = file_dt.replace(tzinfo=None)
            # Check if the date falls within the desired range (inclusive)
            if start_dt <= file_dt <= end_dt:
                files_to_process.append((file_dt, p))

    files_to_process.sort(key=lambda x: x[0])  # Sort chronologically
    return files_to_process


def get_available_months_days(notes_dir: Path) -> Dict[Tuple[int, int], List[int]]:
    """Scans notes dir and returns available (year, month) -> [days] mapping."""
    available = defaultdict(list)
    if not notes_dir or not notes_dir.is_dir():
        return {}  # Return empty if dir is invalid

    for p in notes_dir.glob("*.md"):
        file_dt = parse_fname(p.name)
        if file_dt:
            available[(file_dt.year, file_dt.month)].append(file_dt.day)

    # Sort the days within each month
    for month_tuple in available:
        available[month_tuple].sort()
    return dict(sorted(available.items()))  # Sort months chronologically


# --- Content Generation and Summarization ---


def format_header(dt: datetime) -> str:
    """Formats the header for a specific day."""
    return f"## {dt.strftime('%A, %d %B %Y')}\n\n"


def concatenate_notes(
    files_to_process: List[Tuple[datetime, Path]], output_path: Path, title: str
):
    """Concatenates found notes into the output file."""
    if not files_to_process:
        typer.echo("No matching daily notes found for the specified period.")
        # Optionally create an empty file
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as out:
                out.write(f"# {title}\n\n")
                out.write("No notes found in this period.\n")
            typer.echo(f"Wrote empty report -> {output_path}")
        except IOError as e:
            typer.echo(f"Error writing empty report to {output_path}: {e}", err=True)
            raise typer.Exit(code=1)
        return

    typer.echo(
        f"Found {len(files_to_process)} files. Concatenating into: {output_path}"
    )
    try:
        output_path.parent.mkdir(
            parents=True, exist_ok=True
        )  # Ensure output directory exists
        with open(output_path, "w", encoding="utf-8") as out:
            out.write(f"# {title}\n\n")
            for dt, path in files_to_process:
                out.write(format_header(dt))
                try:
                    out.write(path.read_text(encoding="utf-8"))
                except Exception as e:
                    typer.echo(f"Error reading file {path}: {e}", err=True)
                    # Optionally write error marker in output
                    out.write(f"\n\n--- Error reading file {path.name} ---\n\n")
                out.write("\n\n")  # Add separation between days
        typer.echo(f"Successfully wrote concatenated notes -> {output_path}")
    except IOError as e:
        typer.echo(f"Error writing to output file {output_path}: {e}", err=True)
        raise typer.Exit(code=1)


def create_summary_prompt(notes_content: str) -> str:
    """Creates the prompt to send to the LLM for summarization."""
    # --- Customize this prompt extensively! ---
    prompt = f"""
You are an expert assistant tasked with summarizing daily notes.
The following text contains concatenated daily entries, each starting with a header like '## Monday, 01 April 2024'.

Analyze the entire text provided below and generate a concise summary log. Focus on:
- Key activities, events, or accomplishments.
- Important decisions made or problems solved.
- Recurring themes, topics, or ongoing projects mentioned.
- Any significant insights or reflections recorded.

Format the output as a clear, coherent summary. You can use bullet points or paragraphs as appropriate. Do not just list dates; synthesize the information.

Here are the notes:
--- START OF NOTES ---
{notes_content}
--- END OF NOTES ---

Provide the summary log now:
"""
    return prompt


def summarize_with_llm(input_text: str, model_name: str) -> str:
    """Gets summary from local LLM via Ollama."""
    if not input_text.strip():
        return "Input content was empty. No summary generated."

    full_prompt = create_summary_prompt(input_text)

    try:
        # Ensure the Ollama service is running!
        client = ollama.Client()  # Connects to http://localhost:11434 by default

        typer.echo(
            f"Sending request to local model '{model_name}' for summarization..."
        )
        # Use ollama.chat for models tuned for chat/instruction-following
        response = client.chat(
            model=model_name,
            messages=[
                {"role": "user", "content": full_prompt},
            ],
        )
        summary = response["message"]["content"]
        typer.echo("Summary received from LLM.")
        return summary

    except ConnectionRefusedError:
        typer.echo("\nError: Could not connect to Ollama.", err=True)
        typer.echo(
            "Please ensure the Ollama application or service is running.", err=True
        )
        raise typer.Exit(code=1)
    except ollama.ResponseError as e:
        typer.echo(f"\nError from Ollama API: {e}", err=True)
        if e.status_code == 404:
            typer.echo(
                f"Model '{model_name}' not found. Have you pulled it? Run: ollama pull {model_name}",
                err=True,
            )
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(
            f"An unexpected error occurred while interacting with Ollama: {e}", err=True
        )
        raise typer.Exit(code=1)


# --- Typer Application Setup ---

app = typer.Typer(help="CLI tool to aggregate and summarize daily notes.")
config_app = typer.Typer(help="Manage configuration settings.")
app.add_typer(config_app, name="config")

# --- Configuration Commands ---


@config_app.command("set-path", help="Set the absolute path to your notes directory.")
def set_path(
    notes_path: Path = typer.Argument(
        ...,
        help="The directory containing your daily notes (.md files).",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
):
    config = load_config()
    config["notes_path"] = str(notes_path)
    save_config(config)
    typer.echo(f"Notes path set to: {notes_path}")


@config_app.command("show-path", help="Display the currently configured notes path.")
def show_path():
    notes_dir = get_notes_path()
    if notes_dir:
        typer.echo(f"Current notes path: {notes_dir}")
    else:
        typer.echo(
            "Notes path is not set. Use 'wdid config set-path /path/to/your/notes'"
        )
        raise typer.Exit(code=1)


# --- Core Commands ---


@app.command("choose", help="Interactively choose month and days to generate a report.")
def choose_interactive(
    output_file: Path = typer.Argument(
        ...,
        help="Path to save the generated report (.md).",
        dir_okay=False,
        writable=True,
    ),
    summarize: bool = typer.Option(
        False,
        "--summarize",
        "-s",
        help="Also generate an LLM summary of the chosen notes.",
    ),
    model_name: str = typer.Option(
        "llama3:8b",
        "--model",
        "-m",
        help="Ollama model to use for summarization (if --summarize is active).",
    ),
):
    notes_dir = get_notes_path()
    if not notes_dir:
        typer.echo(
            "Error: Notes path not set. Please set it using 'wdid config set-path <path>'",
            err=True,
        )
        raise typer.Exit(code=1)

    available_months = get_available_months_days(notes_dir)
    if not available_months:
        typer.echo(f"Error: No valid note files found in {notes_dir}", err=True)
        raise typer.Exit(code=1)

    # --- Month Selection ---
    month_choices = [
        datetime(year, month, 1).strftime("%B %Y")
        for year, month in available_months.keys()
    ]
    questions = [
        inquirer.List(
            "month",
            message="Select the month",
            choices=month_choices,
        ),
    ]
    try:
        answers = inquirer.prompt(questions)
        if not answers:
            raise KeyboardInterrupt  # Handle Ctrl+C
    except KeyboardInterrupt:
        typer.echo("\nOperation cancelled by user.")
        raise typer.Exit()

    selected_month_str = answers["month"]
    selected_dt = datetime.strptime(selected_month_str, "%B %Y")
    selected_year, selected_month = selected_dt.year, selected_dt.month
    days_in_month = sorted(available_months.get((selected_year, selected_month), []))

    if not days_in_month:
        typer.echo(
            f"Error: No notes found for {selected_month_str}", err=True
        )  # Should not happen if logic is correct
        raise typer.Exit(code=1)

    # --- Day Range Selection ---
    min_day, max_day = days_in_month[0], days_in_month[-1]
    day_range_choices = ["All available days", "Select specific range"]
    questions = [
        inquirer.List(
            "range_type",
            message=f"Select day range for {selected_month_str} (Available: {min_day}-{max_day})",
            choices=day_range_choices,
        ),
    ]
    try:
        answers = inquirer.prompt(questions)
        if not answers:
            raise KeyboardInterrupt
    except KeyboardInterrupt:
        typer.echo("\nOperation cancelled by user.")
        raise typer.Exit()

    if answers["range_type"] == "All available days":
        start_day = min_day
        end_day = max_day
    else:
        # Get specific start/end days
        questions = [
            inquirer.Text(
                "start_day",
                message=f"Enter start day ({min_day}-{max_day})",
                validate=lambda _, x: x.isdigit() and min_day <= int(x) <= max_day,
            ),
            inquirer.Text(
                "end_day",
                message=f"Enter end day ({min_day}-{max_day})",
                validate=lambda ans, x: x.isdigit()
                and int(ans["start_day"]) <= int(x) <= max_day,
            ),
        ]
        try:
            day_answers = inquirer.prompt(questions)
            if not day_answers:
                raise KeyboardInterrupt
            start_day = int(day_answers["start_day"])
            end_day = int(day_answers["end_day"])
        except KeyboardInterrupt:
            typer.echo("\nOperation cancelled by user.")
            raise typer.Exit()
        except Exception as e:  # Catch validation errors etc.
            typer.echo(f"\nInvalid input: {e}")
            raise typer.Exit(code=1)

    # --- Generate Report ---
    try:
        start_dt = datetime(selected_year, selected_month, start_day)
        end_dt = datetime(selected_year, selected_month, end_day)  # Inclusive end
    except ValueError as e:
        typer.echo(
            f"Error: Invalid date created - {e}", err=True
        )  # Should be caught by validation, but safety first
        raise typer.Exit(code=1)

    report_title = f"Report for {selected_month_str}, Days {start_day}-{end_day}"
    files_to_process = find_notes_in_range(notes_dir, start_dt, end_dt)

    # Make output path absolute before potentially reading it later
    output_file = output_file.resolve()

    concatenate_notes(files_to_process, output_file, report_title)

    # --- Optional LLM Summarization ---
    if summarize:
        typer.echo("-" * 20)
        try:
            concatenated_text = output_file.read_text(encoding="utf-8")
            llm_summary = summarize_with_llm(concatenated_text, model_name)

            # Overwrite the file with summary + original title
            typer.echo(f"Overwriting {output_file} with LLM summary...")
            with open(output_file, "w", encoding="utf-8") as out:
                out.write(f"# {report_title} (LLM Summary)\n\n")
                out.write(llm_summary)
            typer.echo("LLM summary saved.")

        except FileNotFoundError:
            typer.echo(
                f"Error: Could not read back concatenated file {output_file} for summarization.",
                err=True,
            )
            # Don't exit, concatenation already succeeded
        except Exception as e:
            typer.echo(f"Error during LLM summarization phase: {e}", err=True)
            # Don't exit


@app.command(
    "generate", help="Generate a report for a specific date range (non-interactive)."
)
def generate_non_interactive(
    output_file: Path = typer.Argument(
        ...,
        help="Path to save the generated report (.md).",
        dir_okay=False,
        writable=True,
    ),
    start_date: Optional[datetime] = typer.Option(
        None,
        "--start",
        "-s",
        help="Start date (YYYY-MM-DD). Use with --end.",
        formats=["%Y-%m-%d"],
    ),
    end_date: Optional[datetime] = typer.Option(
        None,
        "--end",
        "-e",
        help="End date (YYYY-MM-DD, inclusive). Use with --start.",
        formats=["%Y-%m-%d"],
    ),
    month: Optional[str] = typer.Option(
        None,
        "--month",
        help="Month (YYYY-MM). Use with --start-day/--end-day or alone for full month.",
    ),
    start_day: Optional[int] = typer.Option(
        None, "--start-day", help="Start day of the month (use with --month)."
    ),
    end_day: Optional[int] = typer.Option(
        None, "--end-day", help="End day of the month (inclusive, use with --month)."
    ),
):
    notes_dir = get_notes_path()
    if not notes_dir:
        typer.echo(
            "Error: Notes path not set. Please set it using 'wdid config set-path <path>'",
            err=True,
        )
        raise typer.Exit(code=1)

    # --- Determine date range based on input ---
    if month:
        if start_date or end_date:
            typer.echo("Error: Cannot use --month with --start/--end.", err=True)
            raise typer.Exit(code=1)
        try:
            year, mon = map(int, month.split("-"))
            if not (1 <= mon <= 12):
                raise ValueError("Month out of range")
            _, last_day_of_month = calendar.monthrange(year, mon)

            s_day = start_day if start_day is not None else 1
            e_day = end_day if end_day is not None else last_day_of_month

            if not (1 <= s_day <= last_day_of_month):
                raise ValueError("Start day invalid")
            if not (1 <= e_day <= last_day_of_month):
                raise ValueError("End day invalid")
            if s_day > e_day:
                raise ValueError("Start day cannot be after end day")

            start_dt = datetime(year, mon, s_day)
            end_dt = datetime(
                year, mon, e_day
            )  # End of the day for comparison? No, keep as start for consistency.
            report_title = (
                f"Report for {start_dt.strftime('%B %Y')}, Days {s_day}-{e_day}"
            )

        except ValueError as e:
            typer.echo(f"Error parsing month/day arguments: {e}", err=True)
            raise typer.Exit(code=1)

    elif start_date and end_date:
        if month or start_day or end_day:
            typer.echo(
                "Error: Cannot use --start/--end with --month/--start-day/--end-day.",
                err=True,
            )
            raise typer.Exit(code=1)
        if start_date > end_date:
            typer.echo("Error: Start date cannot be after end date.", err=True)
            raise typer.Exit(code=1)
        start_dt = start_date
        end_dt = end_date
        report_title = f"Report from {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
    else:
        typer.echo(
            "Error: Must provide either (--start and --end dates) or (--month with optional --start-day/--end-day).",
            err=True,
        )
        raise typer.Exit(code=1)

    # --- Find and Concatenate ---
    files_to_process = find_notes_in_range(notes_dir, start_dt, end_dt)
    concatenate_notes(files_to_process, output_file.resolve(), report_title)


@app.command(
    "summarize",
    help="Generate an LLM summary from an existing concatenated notes file.",
)
def summarize_existing(
    input_file: Path = typer.Argument(
        ...,
        help="Path to the existing concatenated notes file.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    output_file: Path = typer.Argument(
        ...,
        help="Path to save the generated summary (.md).",
        dir_okay=False,
        writable=True,
    ),
    model_name: str = typer.Option(
        "llama3:8b", "--model", "-m", help="Ollama model to use for summarization."
    ),
):
    try:
        typer.echo(f"Reading input file: {input_file}")
        input_text = input_file.read_text(encoding="utf-8")
    except Exception as e:
        typer.echo(f"Error reading input file {input_file}: {e}", err=True)
        raise typer.Exit(code=1)

    llm_summary = summarize_with_llm(input_text, model_name)

    try:
        typer.echo(f"Writing LLM summary to: {output_file}")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as out:
            # Add a generic title
            out.write(f"# LLM Summary of {input_file.name}\n\n")
            out.write(llm_summary)
        typer.echo("Summary successfully saved.")
    except IOError as e:
        typer.echo(f"Error writing output file {output_file}: {e}", err=True)
        raise typer.Exit(code=1)


# --- Main Entry Point ---

if __name__ == "__main__":
    app()  # Typer handles the execution
