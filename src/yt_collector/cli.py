from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .collector import YouTubeCollector
from .config import load_settings
from .exporters import export_csv, export_json
from .mock_client import MockYouTubeClient
from .youtube_client import YouTubeDataApiClient
from .transcripts import enrich_collection_file
from .scrapling_probe import proxy_from_env, write_scrapling_collection_transcripts, write_scrapling_transcript_probe

app = typer.Typer(no_args_is_help=True, help="Collect public YouTube video/channel metadata into JSON or CSV.")
@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)



@app.command()
def collect(
    url: Annotated[str | None, typer.Option("--url", help="Single public YouTube watch/shorts/youtu.be URL.")] = None,
    urls_file: Annotated[
        Path | None,
        typer.Option("--urls-file", exists=True, file_okay=True, dir_okay=False, readable=True, help="Text file with one URL per line."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=0, help="Real API upload playlist video limit; 0 means all public upload playlist videos. Mock mode always returns 3.")] = 3,
    output_format: Annotated[str, typer.Option("--format", help="Output format: json or csv.")] = "json",
    out: Annotated[Path, typer.Option("--out", help="Output file path.")] = Path("output/result.json"),
    mock: Annotated[bool, typer.Option("--mock", help="Force mock mode even when YOUTUBE_API_KEY exists.")] = False,
    env_file: Annotated[Path, typer.Option("--env-file", help="Path to .env file for YOUTUBE_API_KEY.")] = Path(".env"),
) -> None:
    urls = _load_urls(url=url, urls_file=urls_file)
    settings = load_settings(env_file)
    mode = "mock" if mock or not settings.youtube_api_key else "real"

    if mode == "mock" and not mock and not settings.youtube_api_key:
        typer.echo("YOUTUBE_API_KEY was not found; using mock mode.", err=True)

    client = (
        MockYouTubeClient()
        if mode == "mock"
        else YouTubeDataApiClient(
            settings.youtube_api_key or "",
            base_url=settings.api_base_url,
            timeout=settings.timeout_seconds,
        )
    )
    collector = YouTubeCollector(client, mode=mode)
    effective_limit = None if limit == 0 else limit
    results = [collector.collect(raw_url, limit=effective_limit) for raw_url in urls]

    normalized_format = output_format.strip().lower()
    if normalized_format == "json":
        output_path = export_json(results, out)
    elif normalized_format == "csv":
        output_path = export_csv(results, out)
    else:
        raise typer.BadParameter("--format must be either 'json' or 'csv'.")

    error_count = sum(1 for result in results if result.errors)
    warning_count = sum(1 for result in results if result.warnings)
    typer.echo(f"Wrote {len(results)} collection result(s) to {output_path} in {mode} mode.")
    if warning_count:
        typer.echo(f"Completed with warnings in {warning_count} result(s).", err=True)
    if error_count:
        typer.echo(f"Completed with errors in {error_count} result(s); see output file for details.", err=True)
    if error_count == len(results):
        raise typer.Exit(code=1)


@app.command()
def transcripts(
    collection: Annotated[
        Path,
        typer.Option(
            "--collection",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Existing JSON collection result from `collect`.",
        ),
    ],
    limit: Annotated[int, typer.Option("--limit", min=0, help="Top ranked channel videos to enrich; 0 means all ranked videos.")] = 20,
    out: Annotated[Path, typer.Option("--out", help="Output transcript-enriched JSON path.")] = Path("output/transcripts.json"),
    language: Annotated[str, typer.Option("--language", help="Preferred caption language code.")] = "ko",
    existing: Annotated[
        Path | None,
        typer.Option("--existing", exists=True, file_okay=True, dir_okay=False, readable=True, help="Existing transcript JSON to reuse as a cache."),
    ] = None,
    sleep_seconds: Annotated[float, typer.Option("--sleep-seconds", min=0.0, help="Delay between uncached transcript requests.")] = 0.0,
    stop_on_ip_block: Annotated[bool, typer.Option("--stop-on-ip-block", help="Stop requesting after the first IP-block transcript error.")] = False,
    include_non_shorts: Annotated[
        bool,
        typer.Option("--include-non-shorts", help="Include non-Shorts videos instead of filtering to is_probably_short."),
    ] = False,
) -> None:
    """Enrich a collection JSON with public caption/transcript text."""
    output_path = enrich_collection_file(
        collection,
        out,
        limit=limit,
        preferred_language=language,
        include_non_shorts=include_non_shorts,
        existing_path=existing,
        sleep_seconds=sleep_seconds,
        stop_on_ip_block=stop_on_ip_block,
    )
    typer.echo(f"Wrote transcript enrichment to {output_path}.")

@app.command()
def scrapling_transcript(
    url: Annotated[str, typer.Option("--url", help="Single public YouTube watch/shorts/youtu.be URL.")],
    out: Annotated[Path, typer.Option("--out", help="Output Scrapling transcript probe JSON path.")] = Path("output/scrapling_transcript_probe.json"),
    language: Annotated[str, typer.Option("--language", help="Preferred rendered transcript language code.")] = "ko",
    timeout_ms: Annotated[int, typer.Option("--timeout-ms", min=10_000, help="Scrapling browser timeout in milliseconds.")] = 90_000,
    wait_ms: Annotated[int, typer.Option("--wait-ms", min=0, help="Maximum post-load DOM settle wait before condition-based transcript checks.")] = 500,
    headless: Annotated[bool, typer.Option("--headless/--headed", help="Run Scrapling browser in headless mode.")] = True,
    proxy: Annotated[str | None, typer.Option("--proxy", help="Optional proxy URL; defaults to SCRAPLING_PROXY_URL when set.")] = None,
) -> None:
    """Probe one public YouTube rendered DOM transcript through Scrapling."""
    output_path = write_scrapling_transcript_probe(
        url,
        out,
        preferred_language=language,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        headless=headless,
        proxy=proxy or proxy_from_env(),
    )
    typer.echo(f"Wrote Scrapling transcript probe to {output_path}.")


@app.command()
def scrapling_transcripts(
    collection: Annotated[
        Path,
        typer.Option(
            "--collection",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Existing JSON collection result from `collect`.",
        ),
    ],
    limit: Annotated[int, typer.Option("--limit", min=0, help="Top ranked channel videos to enrich through Scrapling; 0 means all ranked videos.")] = 20,
    out: Annotated[Path, typer.Option("--out", help="Output Scrapling transcript-enriched JSON path.")] = Path("output/scrapling_transcripts.json"),
    language: Annotated[str, typer.Option("--language", help="Preferred rendered transcript language code.")] = "ko",
    timeout_ms: Annotated[int, typer.Option("--timeout-ms", min=10_000, help="Scrapling browser timeout in milliseconds.")] = 90_000,
    wait_ms: Annotated[int, typer.Option("--wait-ms", min=0, help="Maximum post-load DOM settle wait before condition-based transcript checks.")] = 500,
    sleep_seconds: Annotated[float, typer.Option("--sleep-seconds", min=0.0, help="Delay between Scrapling transcript requests.")] = 0.0,
    stop_on_block: Annotated[bool, typer.Option("--stop-on-block/--keep-going", help="Stop after the first block-looking Scrapling response.")] = True,
    headless: Annotated[bool, typer.Option("--headless/--headed", help="Run Scrapling browser in headless mode.")] = True,
    proxy: Annotated[str | None, typer.Option("--proxy", help="Optional proxy URL; defaults to SCRAPLING_PROXY_URL when set.")] = None,
    include_non_shorts: Annotated[
        bool,
        typer.Option("--include-non-shorts", help="Include non-Shorts videos instead of filtering to is_probably_short."),
    ] = False,
) -> None:
    """Enrich a collection JSON with rendered DOM transcripts through Scrapling."""
    output_path = write_scrapling_collection_transcripts(
        collection,
        out,
        limit=limit,
        preferred_language=language,
        include_non_shorts=include_non_shorts,
        timeout_ms=timeout_ms,
        wait_ms=wait_ms,
        headless=headless,
        proxy=proxy or proxy_from_env(),
        sleep_seconds=sleep_seconds,
        stop_on_block=stop_on_block,
    )
    typer.echo(f"Wrote Scrapling transcript enrichment to {output_path}.")

def _load_urls(*, url: str | None, urls_file: Path | None) -> list[str]:
    urls: list[str] = []
    if url:
        urls.append(url.strip())
    if urls_file:
        urls.extend(
            line.strip()
            for line in urls_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not urls:
        raise typer.BadParameter("Provide --url or --urls-file.")
    return urls


def main() -> None:
    app()


if __name__ == "__main__":
    main()
