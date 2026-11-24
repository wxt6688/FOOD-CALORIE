"""拍照识食物卡路里 —— 零第三方依赖的本地 Web 服务。

启动：python app.py        （默认 http://127.0.0.1:8000）
手机访问：HOST=0.0.0.0 python app.py 后用电脑局域网 IP 打开
仅使用 Python 标准库：http.server / sqlite3 / json / urllib
"""

import json
import os
import sqlite3
import sys
import traceback
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import engine

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "history.db")
MAX_BODY = 20 * 1024 * 1024  # 20MB，足够存放压缩后的图片

CFG = engine.load_config()


# ---------------------------------------------------------------- 数据库

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """CREATE TABLE IF NOT EXISTS records (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             created_at TEXT NOT NULL,
             items TEXT NOT NULL,
             kcal REAL NOT NULL,
             protein REAL NOT NULL,
             fat REAL NOT NULL,
             carb REAL NOT NULL,
             mode TEXT NOT NULL
           )"""
    )
    con.commit()
    con.close()


def db_conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def list_records(limit=50):
    con = db_conn()
    rows = con.execute(
        "SELECT * FROM records ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "items": json.loads(r["items"]),
                "kcal": r["kcal"],
                "protein": r["protein"],
                "fat": r["fat"],
                "carb": r["carb"],
                "mode": r["mode"],
            }
        )
    return out


def today_summary():
    con = db_conn()
    row = con.execute(
        """SELECT COUNT(*) AS cnt,
                  COALESCE(SUM(kcal), 0) AS kcal,
                  COALESCE(SUM(protein), 0) AS protein,
                  COALESCE(SUM(fat), 0) AS fat,
                  COALESCE(SUM(carb), 0) AS carb
           FROM records WHERE substr(created_at, 1, 10) = ?""",
        (today_str(),),
    ).fetchone()
    con.close()
    return {
        "count": row["cnt"],
        "kcal": round(row["kcal"]),
        "protein": round(row["protein"], 1),
        "fat": round(row["fat"], 1),
        "carb": round(row["carb"], 1),
    }


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "FoodCalorie/1.0"

    def log_message(self, fmt, *args):
        # 精简日志，避免把图片的 base64 打进控制台
        if "/api/analyze" in (self.path or ""):
            print("[%s] POST /api/analyze" % self.log_date_time_string())
        else:
            super().log_message(fmt, *args)

    # ---- 响应工具 ----
    def _send(self, status, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json_ok(self, data):
        self._send(200, {"ok": True, **data})

    def _json_err(self, status, message):
        self._send(status, {"ok": False, "error": message})

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY:
            raise ValueError("图片过大，请压缩后再试")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    # ---- 静态文件 ----
    def _serve_static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        # 阻止目录穿越
        full = os.path.abspath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(os.path.abspath(STATIC_DIR)) or not os.path.isfile(full):
            return self._send(404, "Not Found", "text/plain; charset=utf-8")
        ext = os.path.splitext(full)[1].lower()
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }
        with open(full, "rb") as f:
            self._send(200, f.read(), types.get(ext, "application/octet-stream"))

    # ---- GET ----
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                if path == "/api/state":
                    return self._json_ok(
                        {
                            "mode": CFG["mode"],
                            "model": CFG["model"],
                            "warning": CFG["warning"],
                            "foods_count": len(engine.FOODS),
                            "today": today_summary(),
                            "records": list_records(),
                        }
                    )
                if path == "/api/foods":
                    kw = (query.get("q") or [""])[0]
                    return self._json_ok({"foods": engine.search_foods(kw)})
                return self._json_err(404, "未知接口")
            return self._serve_static(path)
        except Exception:
            traceback.print_exc()
            return self._json_err(500, "服务端错误")

    # ---- POST ----
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            body = self._read_body()
            if path == "/api/analyze":
                image = body.get("image", "")
                if not image.startswith("data:image/"):
                    return self._json_err(400, "请先选择或拍摄一张图片")
                result = engine.analyze(image, CFG)
                return self._json_ok(result)

            if path == "/api/records":
                items = body.get("items") or []
                if not items:
                    return self._json_err(400, "没有可保存的食物")
                total = engine.summarize(items)
                con = db_conn()
                cur = con.execute(
                    """INSERT INTO records
                       (created_at, items, kcal, protein, fat, carb, mode)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        json.dumps(items, ensure_ascii=False),
                        total["kcal"], total["protein"], total["fat"],
                        total["carb"], body.get("mode", "mock"),
                    ),
                )
                con.commit()
                rid = cur.lastrowid
                con.close()
                return self._json_ok(
                    {"id": rid, "today": today_summary(), "records": list_records()}
                )
            return self._json_err(404, "未知接口")
        except ValueError as e:
            return self._json_err(400, str(e))
        except Exception as e:
            traceback.print_exc()
            return self._json_err(500, f"服务端错误: {e}")

    # ---- DELETE ----
    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/records":
            return self._json_err(404, "未知接口")
        rid = (urllib.parse.parse_qs(parsed.query).get("id") or [""])[0]
        try:
            con = db_conn()
            con.execute("DELETE FROM records WHERE id = ?", (int(rid),))
            con.commit()
            con.close()
            return self._json_ok(
                {"today": today_summary(), "records": list_records()}
            )
        except (ValueError, TypeError):
            return self._json_err(400, "记录 ID 无效")
        except Exception as e:
            return self._json_err(500, str(e))


def main():
    init_db()
    host = "0.0.0.0" if os.environ.get("HOST") else "127.0.0.1"
    port = int(os.environ.get("PORT", "8000"))
    label = {
        "mock": "演示模式（无需 API Key）",
        "qwen": f"通义千问 Qwen-VL（{CFG['model']}）",
        "openai": f"OpenAI 兼容接口（{CFG['model']}）",
    }.get(CFG["mode"], CFG["mode"])
    print("=" * 56)
    print("  拍照识食物卡路里  Food Calorie Lens")
    print("=" * 56)
    print(f"  识别引擎 : {label}")
    print(f"  营养库   : {len(engine.FOODS)} 种常见食物")
    print(f"  访问地址 : http://{'localhost' if host == '127.0.0.1' else host}:{port}")
    if CFG["warning"]:
        print(f"  提示     : {CFG['warning']}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 56)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
