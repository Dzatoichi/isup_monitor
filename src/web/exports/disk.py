"""Загрузка подготовленного файла на Диск. Не публикует ссылки и не отправляет письма."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class DeliveryError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DiskService:
    API = "https://cloud-api.yandex.net/v1/disk"

    def __init__(self, token, folder):
        if not token or not folder or not folder.startswith("disk:/") or ".." in folder.split("/"):
            raise DeliveryError("Укажите токен Диска и папку вида disk:/ИСУП Монитор")
        self.token, self.folder = token, folder.rstrip("/")
        self.opener = build_opener(NoRedirect())

    def request(self, method, url, *, data=None, authorized=True):
        headers = {"Accept": "application/json"}
        if authorized:
            headers["Authorization"] = f"OAuth {self.token}"
        else:
            headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        try:
            with self.opener.open(Request(url, method=method, data=data, headers=headers), timeout=90) as response:
                return response.status, response.read()
        except HTTPError as error:
            # Токен, временный URL и тело серверной ошибки в журнал не попадают.
            raise DeliveryError(f"Яндекс Диск вернул HTTP {error.code}") from None
        except (URLError, TimeoutError):
            raise DeliveryError("Яндекс Диск недоступен") from None

    def upload(self, path):
        """Папку создаёт администратор заранее; каждый снимок получает отдельный файл."""
        query = urlencode({"path": f"{self.folder}/{path.name}", "overwrite": "true"})
        _, body = self.request("GET", f"{self.API}/resources/upload?{query}")
        try:
            payload = json.loads(body)
            href = payload["href"]
            parsed = urlsplit(href)
            if (payload.get("method") != "PUT" or parsed.scheme != "https" or parsed.username
                    or parsed.password or not parsed.hostname or not parsed.hostname.endswith(".yandex.net")):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise DeliveryError("Яндекс Диск вернул неизвестный адрес загрузки") from None
        status, _ = self.request("PUT", href, data=path.read_bytes(), authorized=False)
        if status not in {200, 201, 202}:
            raise DeliveryError("Загрузка на Диск не подтверждена")
        return "Принято Диском" if status == 202 else "Загружено"
