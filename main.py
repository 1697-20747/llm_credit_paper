#!/usr/bin/env python3
"""
main.py — CAMELS Credit Analysis System
========================================
Orchestrates the full pipeline:
  1. PDF ingestion → structured JSON
  2. CAMELS financial data extraction
  3. Local LLM analysis (Ollama)
  4. Report assembly with citations
  5. DOCX/PDF output

Usage:
    # Ensure Ollama is running: ollama serve
    python main.py --pdf ./annual_reports/lloyds_2025.pdf --bank "Lloyds Banking Group"

    # Override LLM endpoint (e.g. llama.cpp server):
    python main.py --pdf ./annual_reports/lloyds_2025.pdf --llm-url http://localhost:8080

    # Skip PDF extraction (use existing camels_data.json):
    python main.py --camels-json ./data/lloyds_camels_data.json
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from src.pdf_extractor import PDFExtractor
from src.camels_mapper import CAMELSMapper
from src.llm_client import LLMClient
from src.prompt_builder import PromptBuilder
from src.response_validator import ResponseValidator
from src.report_assembler import ReportAssembler

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "camels-analyst"  # Your fine-tuned Ollama model name
FALLBACK_MODEL = "qwen2.5:14b"    # Use if fine-tuned model not available


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline(
    pdf_path: Path | None,
    bank_name: str,
    llm_url: str,
    model_name: str,
    output_dir: Path,
    camels_json: Path | None = None,
    skip_validation: bool = False,
) -> Path:
    """
    Full pipeline: PDF → CAMELS data → LLM analysis → Credit Paper.
    Returns path to the completed credit paper.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{bank_name.replace(' ', '_')}_{timestamp}"

    logger.info(f"Starting pipeline for: {bank_name}")
    logger.info(f"Run ID: {run_id}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:

        # ── Stage 1: PDF Extraction ───────────────────────────────────────────
        if camels_json:
            logger.info(f"Loading pre-extracted CAMELS data from {camels_json}")
            with open(camels_json) as f:
                camels_data = json.load(f)
        else:
            task = progress.add_task("📄 Extracting PDF...", total=None)

            extractor = PDFExtractor(pdf_path)
            extracted = extractor.extract()

            # Save raw extraction for audit trail
            raw_json = output_dir / f"{run_id}_raw_extraction.json"
            with open(raw_json, "w") as f:
                json.dump(extracted, f, indent=2)
            logger.info(f"Raw extraction saved: {raw_json}")

            progress.update(task, description=f"📄 PDF extracted: {len(extracted['pages'])} pages")

            # ── Stage 2: CAMELS Mapping ───────────────────────────────────────
            progress.update(task, description="📊 Mapping CAMELS metrics...")

            mapper = CAMELSMapper(extracted)
            camels_data = mapper.map()

            # Save CAMELS data for audit trail
            camels_json_path = output_dir / f"{run_id}_camels_data.json"
            with open(camels_json_path, "w") as f:
                json.dump(camels_data, f, indent=2)
            logger.info(f"CAMELS data saved: {camels_json_path}")

            progress.update(task, description=f"✅ CAMELS data extracted")

        # ── Stage 3: LLM Analysis ─────────────────────────────────────────────
        task2 = progress.add_task("🤖 Analysing with LLM...", total=6)

        llm = LLMClient(base_url=llm_url, model=model_name)
        prompt_builder = PromptBuilder(bank_name=bank_name)
        validator = ResponseValidator(camels_data=camels_data)

        pillar_analyses = {}
        pillars = ["capital", "asset_quality", "management", "earnings", "liquidity", "sensitivity"]

        for pillar in pillars:
            progress.update(task2, description=f"🤖 Analysing {pillar.replace('_', ' ').title()}...")

            prompt = prompt_builder.build_pillar_prompt(
                pillar=pillar,
                data=camels_data.get(pillar, {}),
            )

            # Call local LLM (no external API)
            response = await llm.complete(
                messages=[
                    {"role": "system", "content": prompt_builder.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.05,   # Near-deterministic for factual analysis
                max_tokens=2000,
            )

            # Validate — check numbers in response exist in source data
            if not skip_validation:
                validation = validator.validate(pillar=pillar, analysis=response)
                if validation.has_hallucinations:
                    logger.warning(
                        f"Potential hallucinations in {pillar}: {validation.flagged_items}"
                    )
                    response += (
                        f"\n\n⚠️ VALIDATION FLAG: The following values in this analysis "
                        f"could not be verified against extracted source data: "
                        f"{', '.join(validation.flagged_items)}. Manual review required."
                    )

            pillar_analyses[pillar] = response
            progress.advance(task2)
            logger.info(f"Pillar complete: {pillar}")

        # ── Overall Rating ────────────────────────────────────────────────────
        progress.update(task2, description="🤖 Computing overall rating...")
        overall_prompt = prompt_builder.build_overall_rating_prompt(
            pillar_analyses=pillar_analyses,
            camels_data=camels_data,
        )
        overall_rating = await llm.complete(
            messages=[
                {"role": "system", "content": prompt_builder.system_prompt},
                {"role": "user", "content": overall_prompt},
            ],
            temperature=0.05,
            max_tokens=1500,
        )

        # ── Stage 4: Report Assembly ──────────────────────────────────────────
        task3 = progress.add_task("📝 Assembling credit paper...", total=None)

        assembler = ReportAssembler(
            bank_name=bank_name,
            run_id=run_id,
            camels_data=camels_data,
            pillar_analyses=pillar_analyses,
            overall_rating=overall_rating,
        )

        # Markdown report
        md_path = output_dir / f"{run_id}_credit_paper.md"
        assembler.to_markdown(md_path)
        logger.info(f"Markdown report: {md_path}")

        # DOCX report
        docx_path = output_dir / f"{run_id}_credit_paper.docx"
        assembler.to_docx(docx_path)
        logger.info(f"DOCX report: {docx_path}")

        # Audit index (every claim → source)
        audit_path = output_dir / f"{run_id}_audit_index.json"
        assembler.to_audit_index(audit_path)
        logger.info(f"Audit index: {audit_path}")

        progress.update(task3, description="✅ Credit paper complete")

    console.print(f"\n[bold green]✅ Credit paper complete[/bold green]")
    console.print(f"[cyan]📄 Report:[/cyan] {docx_path}")
    console.print(f"[cyan]📋 Audit index:[/cyan] {audit_path}")

    return docx_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--pdf", "pdf_path", type=click.Path(exists=True), default=None,
              help="Path to annual report PDF")
@click.option("--bank", "bank_name", default="Bank", show_default=True,
              help="Bank name for the report")
@click.option("--llm-url", default=DEFAULT_OLLAMA_URL, show_default=True,
              help="Local LLM server URL (Ollama or llama.cpp)")
@click.option("--model", "model_name", default=DEFAULT_MODEL, show_default=True,
              help="Ollama model name")
@click.option("--output-dir", default="./output", show_default=True,
              help="Output directory for reports")
@click.option("--camels-json", type=click.Path(exists=True), default=None,
              help="Skip PDF extraction; use existing CAMELS JSON")
@click.option("--skip-validation", is_flag=True, default=False,
              help="Skip hallucination validation (faster)")
@click.option("--verbose", is_flag=True, default=False)
def main(pdf_path, bank_name, llm_url, model_name, output_dir,
         camels_json, skip_validation, verbose):
    """
    CAMELS Credit Analysis System — Local LLM Edition.

    Generates an auditable bank credit paper using the CAMELS framework,
    powered by a locally-running post-trained Qwen2.5 model.

    Examples:
        python main.py --pdf lloyds_2025.pdf --bank "Lloyds Banking Group"
        python main.py --camels-json ./data/lloyds_camels.json --bank "Lloyds"
    """
    if verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO")

    if not pdf_path and not camels_json:
        raise click.UsageError("Either --pdf or --camels-json must be provided.")

    console.print(f"\n[bold]CAMELS Credit Analysis System[/bold]")
    console.print(f"Bank: [cyan]{bank_name}[/cyan]")
    console.print(f"LLM:  [cyan]{llm_url}[/cyan] / model: [cyan]{model_name}[/cyan]")
    console.print(f"Mode: [yellow]100% local — no external API calls[/yellow]\n")

    asyncio.run(run_pipeline(
        pdf_path=Path(pdf_path) if pdf_path else None,
        bank_name=bank_name,
        llm_url=llm_url,
        model_name=model_name,
        output_dir=Path(output_dir),
        camels_json=Path(camels_json) if camels_json else None,
        skip_validation=skip_validation,
    ))


if __name__ == "__main__":
    main()
