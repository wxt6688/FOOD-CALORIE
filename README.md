# Food Calorie Lens · 拍照识食物卡路里

上传或拍摄一张餐盘照片，自动识别其中的食物、估计份量，并按内置食物营养库计算热量与三大营养素。

零第三方依赖，`python app.py` 即可运行。默认演示模式不需要任何 API Key，配置后即可切换为真实视觉识别。

---

## 功能

- 取图：点击选择、拖拽上传、调用摄像头拍摄；手机浏览器会直接唤起相机
- 识别：演示模式（本地模拟）或接入视觉大模型（通义千问 Qwen-VL / 任意 OpenAI 兼容接口）
- 份量可调：每样食物的克重可用滑块或加减按钮调整，热量与营养素实时重算
- 营养汇总：环形日目标进度、三大营养素供能占比堆叠条
- 记录：一键保存到本机 SQLite，按日汇总累计热量与餐数
- 食物库：内置 70 种常见中西餐/饮品/水果的每 100g 营养数据，支持搜索手动添加
- 无网可用：营养库与计算全部在本地，只有真实识别时才需要联网

## 设计取舍：模型只负责"是什么"，热量由程序算

这是本项目与多数同类 Demo 的关键区别。

大模型直接报"这份红烧肉 520 大卡"看起来很爽，但数字无法核查、每次问还可能不一样。本项目把职责切开：

| 环节 | 由谁负责 |
| --- | --- |
| 认出是什么食物 | 视觉模型 |
| 估计多少克 | 视觉模型 |
| 每 100g 的热量与营养素 | `food_db.json`（可核查、可修改） |
| 该份实际摄入量 | 程序按 `克重 / 100 × 每100g值` 计算 |

模型识别出的食物名会先在营养库里做精确匹配，再做包含匹配（"一碗白米饭"也能命中"白米饭"）。命中则完全使用库中数据，标注 `营养库`；未命中才回退到模型常识，并明确标注 `模型估算`。这样每个数字都有出处。

## 快速开始

要求 Python 3.8+（开发验证环境为 3.13），不需要安装任何第三方包。

```bash
cd food-calorie-app
python app.py
```

浏览器打开 http://127.0.0.1:8000

手机访问（同一局域网）：

```bash
# Windows Git Bash / macOS / Linux
HOST=0.0.0.0 python app.py
```

然后用电脑的局域网 IP 打开，例如 `http://192.168.1.8:8000`。首次使用摄像头需要浏览器授权，非 localhost 访问时部分浏览器要求 HTTPS。

## 接入真实视觉识别

复制配置模板，按需填写：

```bash
cp .env.example .env
```

### 方式一：通义千问 Qwen-VL（阿里云百炼）

```ini
FOOD_ENGINE=qwen
DASHSCOPE_API_KEY=sk-你的key
QWEN_MODEL=qwen-vl-plus
```

Key 在 https://dashscope.aliyuncs.com 申请，新用户有免费额度。

### 方式二：任意 OpenAI 兼容视觉接口

豆包（火山方舟）、GLM-4V、OpenRouter 免费模型、本地 vLLM / Ollama 都可以，只要兼容 `/chat/completions` 且模型支持图片输入：

```ini
FOOD_ENGINE=openai
OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/chat/completions
OPENAI_API_KEY=你的key
OPENAI_MODEL=你的视觉模型 endpoint id
```

重启服务后，页面右上角徽章会从「演示模式」变成「真实识别」。若 Key 无效或接口报错，服务会自动降级回演示数据并在页面提示原因，不会白屏。

## HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/state` | 当前引擎、营养库数量、今日汇总、历史记录 |
| POST | `/api/analyze` | 请求体 `{"image":"data:image/jpeg;base64,..."}`，返回识别结果 |
| POST | `/api/records` | 保存一餐，请求体 `{"items":[...],"mode":"mock"}` |
| DELETE | `/api/records?id=1` | 删除一条记录 |
| GET | `/api/foods?q=米饭` | 搜索营养库 |

`/api/analyze` 返回结构：

```json
{
  "ok": true,
  "mode": "qwen",
  "items": [
    {
      "name": "番茄炒蛋", "grams": 180, "category": "荤菜",
      "kcal_per_100": 95, "protein_per_100": 5.2,
      "fat_per_100": 6.8, "carb_per_100": 3.5,
      "kcal": 171, "protein": 9.4, "fat": 12.2, "carb": 6.3,
      "confidence": 0.91, "source": "营养库"
    }
  ],
  "total": { "kcal": 171, "protein": 9.4, "fat": 12.2, "carb": 6.3, "count": 1 },
  "advice": "脂肪占比偏高，可减少红烧与油炸做法。",
  "note": "识别名称与份量由视觉模型给出；热量与营养素由内置营养库按克重计算。"
}
```

## 目录结构

```
food-calorie-app/
├── app.py                 # HTTP 服务、路由、SQLite 记录（标准库实现）
├── engine.py              # 识别引擎：mock / qwen / openai 三模式，结果归一化
├── food_db.json           # 70 种食物的每 100g 营养数据
├── static/
│   ├── index.html         # 页面结构
│   ├── app.css            # 样式
│   └── app.js             # 取图、压缩、识别、克重联动、渲染
├── .env.example           # 配置模板
├── requirements.txt       # 说明本项目无第三方依赖
└── data/history.db        # 运行后自动生成的 SQLite 数据库（已忽略）
```

## 准确率与局限

最大的误差来源不是识别错菜名，而是份量估计。单张 RGB 照片没有深度信息，克重只能靠先验推断。Nutrition5k 论文给出的参考值是：普通人估算相对误差约 53%，专业营养师约 41%，经过微调的视觉模型可以做到 15%~30%。

所以本项目默认可调克重，并把这当作正式功能而不是补丁。此外：

- 演示模式的数据是按图片哈希生成的模拟值，**不是真实识别**，仅用于跑通流程
- 浓汤、盖浇饭、火锅这类混合菜品的份量估计误差会明显更大
- 所有结果仅供学习与参考，不构成医学或营养学建议

## 相关开源项目调研

做这个项目前对比过的方案，供后续扩展参考：

| 项目 | 地址 | 特点 |
| --- | --- | --- |
| Nutrition5k | github.com/google-research-datasets/Nutrition5k | Google 的 5000 盘真实菜品数据集，含深度图与营养成分，领域基准。仓库已归档，数据仍可下载 |
| DeepLearning-Food-Image-Recognition-And-Calorie-Estimation | github.com/jubins/... | 105 星，TensorFlow 分类 + KNN 估热量，经典入门实现 |
| Calorie-estimation-from-food-images-OpenCV | github.com/meghanamreddy/... | 95 星，传统 CV 做体积估计，思路值得借鉴 |
| Food_Calorie_and_Energy_Estimation_System | github.com/qunshansj/... | 69 星，中文项目，YOLO 检测 + 数据集 + 部署教程 |
| Anqi00/food | github.com/Anqi00/food | FastAPI + 原生前端 + Qwen-VL，最轻量的可用实现 |
| CalorieScan-Food-Calorie-API | github.com/ChenYY-Offical/... | YOLOv8 + SAM + MiDaS 分割与深度，工程链路完整 |
| OmniFood8K | github.com/yudongjian/OmniFood8K-food | CVPR 2026，8036 张多视角中式菜肴 + 营养标注，目前最贴合中餐的单图方案 |
| OpenNutriTracker | github.com/simonoppowa/OpenNutriTracker | 3k 星，Flutter 开源热量追踪 App，条形码 + 手动记录，偏产品化 |
| 膳识 DietSense | gitee.com/limityang/edge-diet-sense | Gitee，FastAPI + React Native 移动端 + 营养库，可无 Key 运行 |
| Food Vision Agent | gitee.com/hwxus/food-vision-agent | Gitee，多供应商大模型故障转移，输出原材料级成分拆解 |

结论：想最快看到效果，用视觉大模型 + 营养库计算（也就是本项目的做法）；想追求精度上限，需要走 Nutrition5k / OmniFood8K 微调路线，代价是数据和算力。

## 分支说明

- `main`：稳定可运行版本
- `dev`：开发分支，后续迭代在此进行

## License

MIT
