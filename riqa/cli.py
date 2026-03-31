"""RIQA CLI entry point."""

import click


@click.group()
@click.version_option(version="0.0.1")
def main():
    """RIQA — Risk-limited receiving inspection QA system."""
    pass


@main.command()
def info():
    """Show system info and configuration status."""
    click.echo("RIQA v0.0.1")
    click.echo("Status: Phase 0 — Feasibility kill test")


if __name__ == "__main__":
    main()
