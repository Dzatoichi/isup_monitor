"""Готовит файлы для корпоративной Алисы из уже сохранённого снимка."""
import argparse
import asyncio
import json
from src.shared.database import db_helper
from src.config import settings
from .service import ExportService, atomic_write
from .disk import DiskService, DeliveryError


async def run(args):
    # Импорт регистрирует все связанные модели SQLAlchemy, но не запускает веб-сервер.
    from src.web.app import app
    try:
        path, manifest = await ExportService.save(args.output_dir, args.snapshot_id,
                                                  set(args.oks) if args.oks else None)
        if args.upload:
            try:
                manifest["disk"] = await asyncio.to_thread(
                    DiskService(settings.YANDEX_DISK_TOKEN.get_secret_value() if settings.YANDEX_DISK_TOKEN else None,
                                settings.YANDEX_DISK_FOLDER).upload, path)
            except DeliveryError:
                manifest["disk"] = "Ошибка отправки; локальный файл сохранён"
                raise
            finally:
                atomic_write(path.with_suffix(".json"), json.dumps(manifest, ensure_ascii=False, indent=2).encode())
        print(f"Снимок {manifest['snapshot_id']}: объектов {manifest['objects']}, записей проверок {manifest['issues']}")
        print(path.resolve())
        return path, manifest
    finally:
        await db_helper.engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id", type=int)
    parser.add_argument("--oks", type=int, nargs="+", help="Пробная выборка номеров ИСУП")
    parser.add_argument("--output-dir", default=settings.ISUP_EXPORT_DIR)
    parser.add_argument("--upload", action="store_true", help="Отправить в настроенную папку Диска")
    args = parser.parse_args()
    if (args.snapshot_id is not None and args.snapshot_id < 1) or (args.oks and min(args.oks) < 1):
        parser.error("Номера снимков и объектов должны быть положительными")
    try:
        asyncio.run(run(args))
    except DeliveryError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
