"""127.0.0.1 전용 사람 검수 화면. 원문 CSV와 AI 라벨을 수정하지 않는다."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading

LABELS = {"긍정", "중립", "부정"}
ROOT = Path(__file__).resolve().parents[1]
VISIBLE = ("stock_id", "post_id", "parent_id", "text_norm", "parent_text", "context_status")


class Conflict(ValueError):
    pass


def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ReviewStore:
    def __init__(self, source, output):
        self.source = Path(source)
        self.output = Path(output)
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with self.source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not set(VISIBLE).issubset(reader.fieldnames or []):
                raise ValueError("부모 맥락 검수 CSV의 필수 컬럼이 없습니다.")
            self.rows = [{key: row[key] for key in VISIBLE} for row in reader]
        if not self.rows or any(not r["stock_id"] or not r["post_id"] for r in self.rows):
            raise ValueError("검수 CSV가 비어 있거나 ID가 없습니다.")
        # 외부 평가기는 post_id만으로 병합하므로 종목 간에도 유일해야 한다.
        if len({r["post_id"] for r in self.rows}) != len(self.rows):
            raise ValueError("중복 post_id: 외부 평가기와 안전하게 연결할 수 없습니다.")
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock_file = (self.output / ".review.lock").open("a")
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            raise ValueError("같은 출력 폴더를 사용하는 검수 도구가 이미 실행 중입니다.") from None
        self.mutex = threading.Lock()
        self.path = self.output / "progress.json"
        self.state = {"source_sha256": self.source_hash, "revision": 0, "records": {}}
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text())
                if saved["source_sha256"] != self.source_hash:
                    raise ValueError("입력 파일이 변경되었습니다. 기존 검수 보호를 위해 새 출력 폴더를 사용하세요.")
                if type(saved["revision"]) is not int or saved["revision"] < 0:
                    raise ValueError("저장된 revision 오류")
                for key, record in saved["records"].items():
                    if not key.isdigit() or not 0 <= int(key) < len(self.rows):
                        raise ValueError("저장된 검수 ID 오류")
                    self.validate_record(record)
                self.state = saved
            except Exception:
                self.close()
                raise

    def close(self):
        self.lock_file.close()

    @staticmethod
    def validate_record(record):
        if record.get("label") not in LABELS | {""}:
            raise ValueError("라벨은 긍정·중립·부정 또는 빈 값이어야 합니다.")
        if type(record.get("uncertain")) is not bool:
            raise ValueError("보류 여부가 올바르지 않습니다.")
        if not isinstance(record.get("note"), str) or len(record["note"]) > 3000:
            raise ValueError("메모는 3,000자 이하여야 합니다.")
        if not isinstance(record.get("reviewer"), str) or not 1 <= len(record["reviewer"].strip()) <= 80:
            raise ValueError("검수자 이름 또는 별칭을 입력하세요(80자 이내).")

    def snapshot(self):
        with self.mutex:
            return {"rows": self.rows, **json.loads(json.dumps(self.state))}

    def save(self, body):
        index = body.get("index")
        if type(index) is not int or not 0 <= index < len(self.rows):
            raise ValueError("검수 항목이 올바르지 않습니다.")
        record = {k: body.get(k) for k in ("label", "uncertain", "note", "reviewer")}
        self.validate_record(record)
        record["reviewer"] = record["reviewer"].strip()
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        with self.mutex:
            if body.get("revision") != self.state["revision"]:
                raise Conflict("다른 탭에서 수정했습니다. 입력을 복사한 뒤 새로고침하세요.")
            updated = {**self.state, "revision": self.state["revision"] + 1,
                       "records": {**self.state["records"], str(index): record}}
            atomic_json(self.path, updated)
            self.state = updated
            return {"revision": updated["revision"]}

    def export(self, revision):
        with self.mutex:
            if revision != self.state["revision"]:
                raise Conflict("검수 상태가 변경되었습니다. 새로고침 후 내보내세요.")
            records = self.state["records"]
            if any(not records.get(str(i), {}).get("label") or records[str(i)]["uncertain"]
                   for i in range(len(self.rows))):
                raise ValueError("모든 항목의 라벨을 저장하고 보류를 해제해야 내보낼 수 있습니다.")
            if hashlib.sha256(self.source.read_bytes()).hexdigest() != self.source_hash:
                raise Conflict("입력 CSV가 변경되었습니다. 내보내기를 중단합니다.")
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=["stock_id", "post_id", "label"])
            writer.writeheader()
            for i, row in enumerate(self.rows):
                writer.writerow({"stock_id": row["stock_id"], "post_id": row["post_id"],
                                 "label": records[str(i)]["label"]})
            content = buffer.getvalue()
            name = "gold-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            directory = self.output / "exports"
            directory.mkdir(exist_ok=True)
            target = directory / (name + ".csv")
            with target.open("x", encoding="utf-8-sig", newline="") as stream:
                stream.write(content)
            atomic_json(directory / (name + ".json"), {
                "source_sha256": self.source_hash, "revision": revision, "rows": len(self.rows),
                "label_origin": "user_entered_in_local_review_tool",
                "reviewers": sorted({r["reviewer"] for r in records.values()}),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "note": "검수자가 직접 입력한 라벨. 독립 평가자 수나 정답 품질을 자동 보증하지 않음.",
            })
            return {"path": str(target.resolve()), "filename": target.name, "csv": content}


def make_server(store, port=8768):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # 원문·사용자 입력·요청값을 로그에 남기지 않는다.

        def respond(self, status, payload, content_type="application/json; charset=utf-8"):
            data = (json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload, dict) else payload)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def trusted(self):
            host = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            return (self.headers.get("Host") == host and
                    (origin is None or origin == f"http://{host}") and
                    self.headers.get("Sec-Fetch-Site") not in {"cross-site", "same-site"})

        def do_GET(self):
            if not self.trusted():
                self.respond(403, {"error": "로컬 동일 출처에서만 접근할 수 있습니다."})
                return
            if self.path == "/api/state":
                self.respond(200, {**store.snapshot(), "token": token})
            elif self.path in {"/", "/app.js", "/style.css"}:
                filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[self.path]
                kind = {"/": "text/html", "/app.js": "text/javascript", "/style.css": "text/css"}[self.path]
                self.respond(200, (Path(__file__).parent / filename).read_bytes(), kind + "; charset=utf-8")
            else:
                self.respond(404, {"error": "페이지를 찾을 수 없습니다."})

        def do_POST(self):
            if not self.trusted() or not secrets.compare_digest(self.headers.get("X-Review-Token", ""), token):
                self.respond(403, {"error": "요청 인증에 실패했습니다. 새로고침하세요."})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 20000:
                    raise ValueError("요청 크기가 올바르지 않습니다.")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("요청 형식이 올바르지 않습니다.")
                if self.path == "/api/save":
                    result = store.save(body)
                elif self.path == "/api/export":
                    result = store.export(body.get("revision"))
                else:
                    self.respond(404, {"error": "지원하지 않는 요청"})
                    return
                self.respond(200, result)
            except Conflict as exc:
                self.respond(409, {"error": str(exc)})
            except (ValueError, TypeError) as exc:
                self.respond(400, {"error": str(exc)})
            except OSError:
                self.respond(500, {"error": "저장에 실패했습니다. 디스크 공간과 권한을 확인하세요."})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/labels/human_review_context_20261021/review.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/labels/human_review_session")
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    for path in (args.input, args.output):
        if not path.resolve().is_relative_to(ROOT / "data"):
            parser.error("검수 입출력은 Git 제외 data 폴더 안에 지정하세요.")
    store = ReviewStore(args.input, args.output)
    try:
        server = make_server(store, args.port)
        print(f"검수 도구: http://127.0.0.1:{server.server_port}", flush=True)
        print(f"검수 {len(store.rows)}건 · AI 예측/가격 숨김 · Ctrl+C로 종료", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        store.close()


if __name__ == "__main__":
    main()
