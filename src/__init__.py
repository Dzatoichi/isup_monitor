"""Точка входа команды isup-monitor."""

def main() -> None:
    """Запускает основной парсер из установленной команды."""
    from .parser.parser import main as run_parser

    run_parser()
