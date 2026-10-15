import contextvars
import json
import logging
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
log = logging.getLogger("karaoke")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if type(h).__name__ == "LogCaptureHandler"] + [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = name != "uvicorn.access"


def log_event(logger: logging.Logger, msg: str, **fields) -> None:
    logger.info(msg, extra={"fields": fields})


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        error = None
        try:
            response = await call_next(request)
        except Exception as exc:
            error = exc
            response = PlainTextResponse("Internal Server Error", status_code=500)
        fields = {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": round((time.perf_counter() - start) * 1000, 1),
        }
        if error is None:
            log_event(log, "request", **fields)
        else:
            log.error("request", extra={"fields": fields}, exc_info=error)
        response.headers["x-request-id"] = rid
        request_id_var.reset(token)
        return response
