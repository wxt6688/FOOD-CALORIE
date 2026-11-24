"""识别引擎：三种可插拔模式，仅依赖 Python 标准库。

模式
  mock    演示模式，无需任何 API Key，用图片哈希生成稳定的模拟识别结果
  qwen    阿里云百炼 Qwen-VL（通义千问视觉模型）
  openai  任意 OpenAI 兼容的视觉接口（豆包 / GLM-4V / OpenRouter / 本地 vLLM 等）

设计原则：模型只负责「认出是什么菜、大概多少克」；
热量与三大营养素一律来自可核对的 food_db.json 并由程序计算，
模型对未知食物给出的估算值会明确标注来源，避免把幻觉数字当成事实。
"""

import base64
import hashlib
import json
import os
import random
import re
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "food_db.json"), encoding="utf-8") as _f:
    FOOD_DB = json.load(_f)

FOODS = FOOD_DB["foods"]
FOOD_INDEX = {f["name"]: f for f in FOODS}


# ---------------------------------------------------------------- 配置

def _load_dotenv():
    """读取同目录下的 .env（不覆盖已经存在的系统环境变量）。"""
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and not os.environ.get(k):
                os.environ[k] = v


def load_config():
    _load_dotenv()
    mode = os.environ.get("FOOD_ENGINE", "mock").strip().lower()
    cfg = {"mode": "mock", "base_url": "", "api_key": "", "model": "", "warning": ""}

    if mode == "qwen":
        key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not key:
            cfg["warning"] = "已选择 qwen 模式但未配置 DASHSCOPE_API_KEY，已自动回退到演示模式。"
        else:
            cfg.update(
                mode="qwen",
                base_url=os.environ.get(
                    "QWEN_BASE_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                ),
                api_key=key,
                model=os.environ.get("QWEN_MODEL", "qwen-vl-plus"),
            )
    elif mode == "openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            cfg["warning"] = "已选择 openai 模式但未配置 OPENAI_API_KEY，已自动回退到演示模式。"
        else:
            cfg.update(
                mode="openai",
                base_url=os.environ.get(
                    "OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"
                ),
                api_key=key,
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            )
    elif mode != "mock":
        cfg["warning"] = f"未知的 FOOD_ENGINE={mode}，已自动回退到演示模式。"
    return cfg


# ---------------------------------------------------------------- 工具

def make_item(name, grams, kcal100, protein100, fat100, carb100,
              confidence=0.9, source="营养库", category="其他"):
    """统一由「每 100g 营养值 × 克重」计算实际摄入量。"""
    grams = max(1, int(round(float(grams))))
    factor = grams / 100.0
    return {
        "name": name,
        "category": category,
        "grams": grams,
        "kcal_per_100": round(float(kcal100), 1),
        "protein_per_100": round(float(protein100), 1),
        "fat_per_100": round(float(fat100), 1),
        "carb_per_100": round(float(carb100), 1),
        "kcal": int(round(float(kcal100) * factor)),
        "protein": round(float(protein100) * factor, 1),
        "fat": round(float(fat100) * factor, 1),
        "carb": round(float(carb100) * factor, 1),
        "confidence": round(float(confidence), 2),
        "source": source,
    }


def summarize(items):
    return {
        "kcal": sum(i["kcal"] for i in items),
        "protein": round(sum(i["protein"] for i in items), 1),
        "fat": round(sum(i["fat"] for i in items), 1),
        "carb": round(sum(i["carb"] for i in items), 1),
        "count": len(items),
    }


# ---------------------------------------------------------------- 演示模式

MOCK_NOTES = [
    "主食搭配荤菜是比较常见的一餐结构，注意蔬菜比例。",
    "这份餐的脂肪占比偏高，可以考虑减少油炸与红烧做法。",
    "蛋白质摄入尚可，建议再补充一份绿叶蔬菜。",
    "整体热量适中，饮品若是含糖饮料可换成无糖版本。",
]


def _mock_analyze(image_data_url):
    raw = image_data_url.split(",", 1)[-1] if "," in image_data_url else image_data_url
    try:
        digest = hashlib.sha256(base64.b64decode(raw)).hexdigest()
    except Exception:
        digest = hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()
    rng = random.Random(int(digest[:12], 16))

    staples = [f for f in FOODS if f["category"] in ("主食", "汤粥")]
    dishes = [f for f in FOODS if f["category"] in ("荤菜", "素菜", "西餐", "快餐")]
    drinks = [f for f in FOODS if f["category"] in ("饮品", "水果")]

    chosen = [rng.choice(staples), rng.choice(dishes)]
    if rng.random() < 0.6:
        chosen.append(rng.choice(dishes + drinks))

    items = []
    for f in chosen:
        grams = int(f["typical"] * rng.uniform(0.7, 1.3))
        items.append(
            make_item(
                f["name"], grams, f["kcal"], f["protein"], f["fat"], f["carb"],
                confidence=round(rng.uniform(0.76, 0.94), 2),
                source="营养库（演示）",
                category=f["category"],
            )
        )
    return {
        "items": items,
        "advice": rng.choice(MOCK_NOTES),
        "mode": "mock",
        "note": "演示模式：结果由图片哈希生成的模拟数据，不是真实识别。配置 API Key 后即可切换为真实视觉识别。",
    }


# ---------------------------------------------------------------- 视觉模型

SYSTEM_PROMPT = """你是一个严谨的饮食营养分析助手。用户会给你一张餐盘照片。
请识别照片中出现的所有食物（中餐、西餐、饮料均要识别），并估计每一项的份量（克或毫升，按 1ml≈1g 处理）。

只输出一个 JSON 对象，不要输出任何解释文字、不要使用 Markdown 代码块。格式如下：
{
  "items": [
    {"name": "番茄炒蛋", "grams": 180, "confidence": 0.9, "category": "荤菜"}
  ],
  "advice": "一句话的饮食建议，不超过 40 字"
}

规则：
1. name 用简体中文的常见菜名或食物名，尽量使用标准名称（例如「白米饭」「红烧肉」「可乐」）。
2. grams 必须是正整数，按普通成年人一份的常见份量估计；拿不准时取偏保守的中位数。
3. confidence 取 0 到 1 之间的数；看不清或不确定时低于 0.6。
4. 只列出你确实能在图中看到的东西，不要臆测；照片里没有食物时 items 返回空数组。
5. 不要估算热量和营养素，这部分由程序的食物营养库计算。
"""


def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型返回内容中没有找到 JSON 对象")
    return json.loads(text[start:end + 1])


def _call_vision_api(image_data_url, cfg):
    payload = {
        "model": cfg["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": "请识别这张照片里的食物并估计份量，按系统提示的 JSON 格式输出。"},
                ],
            },
        ],
    }
    req = urllib.request.Request(
        cfg["base_url"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg["api_key"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError(f"视觉接口返回 HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接视觉接口: {e.reason}") from e

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"视觉接口返回结构异常: {str(body)[:300]}") from e
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return _extract_json(content)


def _lookup(name):
    """精确匹配优先，其次做包含匹配，让「一碗白米饭」也能命中营养库。"""
    if name in FOOD_INDEX:
        return FOOD_INDEX[name]
    for key, value in FOOD_INDEX.items():
        if len(key) >= 2 and (key in name or name in key):
            return value
    return None


def _vision_analyze(image_data_url, cfg):
    data = _call_vision_api(image_data_url, cfg)
    raw_items = data.get("items") or []
    items = []
    for raw in raw_items[:12]:
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        db = _lookup(name)
        if db:
            items.append(
                make_item(
                    db["name"], raw.get("grams", db["typical"]),
                    db["kcal"], db["protein"], db["fat"], db["carb"],
                    confidence=raw.get("confidence", 0.8),
                    source="营养库",
                    category=db["category"],
                )
            )
        else:
            # 库中查不到：回退到模型自带常识，并明确标注为估算值
            kcal = float(raw.get("kcal_per_100", 150) or 150)
            p = float(raw.get("protein_per_100", 6) or 6)
            f = float(raw.get("fat_per_100", 6) or 6)
            c = float(raw.get("carb_per_100", 18) or 18)
            items.append(
                make_item(
                    name, raw.get("grams", 150), kcal, p, f, c,
                    confidence=raw.get("confidence", 0.7),
                    source="模型估算",
                    category=str(raw.get("category", "其他")),
                )
            )
    if not items:
        raise RuntimeError("模型没有在照片中识别出食物，请换一张更清晰的照片。")
    return {
        "items": items,
        "advice": str(data.get("advice", "")).strip()[:120],
        "mode": cfg["mode"],
        "note": "识别名称与份量由视觉模型给出；热量与营养素由内置营养库按克重计算，标注「模型估算」的项目营养值仅供参考。",
    }


# ---------------------------------------------------------------- 对外入口

def analyze(image_data_url, cfg=None):
    cfg = cfg or load_config()
    if cfg["mode"] == "mock":
        result = _mock_analyze(image_data_url)
    else:
        try:
            result = _vision_analyze(image_data_url, cfg)
        except Exception as exc:
            result = _mock_analyze(image_data_url)
            result["mode"] = "mock"
            result["error"] = str(exc)
            result["note"] = (
                f"真实识别失败，已降级为演示数据。原因：{exc}"
            )
    result["total"] = summarize(result["items"])
    if cfg.get("warning"):
        result["warning"] = cfg["warning"]
    return result


def search_foods(keyword="", limit=30):
    keyword = keyword.strip()
    hits = [f for f in FOODS if not keyword or keyword in f["name"]]
    return hits[:limit]
