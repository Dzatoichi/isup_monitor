"""Позволяет запустить парсер как модуль или как файл Python."""

if __name__ == "__main__":
    # При запуске через -m и напрямую Python по-разному ищет соседние модули.
    if __package__:
        from .parser.parser import main
    else:
        from parser.parser import main

    main()
