/* 拍照识食物卡路里 —— 前端交互 */
(() => {
  "use strict";

  const DAILY_GOAL = 2000;      // 每日参考热量目标，可按需修改
  const RING_CIRC = 339.29;     // 2 * PI * 54

  const $ = (id) => document.getElementById(id);
  const state = {
    image: null,
    items: [],
    mode: "mock",
    advice: "",
    saved: false,
    stream: null,
  };

  const els = {
    engineBadge: $("engineBadge"), notice: $("notice"),
    dropZone: $("dropZone"), fileInput: $("fileInput"),
    cameraBox: $("cameraBox"), video: $("video"),
    cameraBtn: $("cameraBtn"), snapBtn: $("snapBtn"), closeCamBtn: $("closeCamBtn"),
    previewWrap: $("previewWrap"), preview: $("preview"), clearBtn: $("clearBtn"),
    analyzeBtn: $("analyzeBtn"), statusText: $("statusText"),
    emptyState: $("emptyState"), resultBody: $("resultBody"), resultHint: $("resultHint"),
    ringFill: $("ringFill"), ringPct: $("ringPct"),
    totalKcal: $("totalKcal"), totalP: $("totalP"), totalF: $("totalF"), totalC: $("totalC"),
    stackP: $("stackP"), stackF: $("stackF"), stackC: $("stackC"),
    items: $("items"), itemCount: $("itemCount"), advice: $("advice"),
    saveBtn: $("saveBtn"), resetBtn: $("resetBtn"), addFoodBtn: $("addFoodBtn"),
    todayKcal: $("todayKcal"), todayCount: $("todayCount"), todayBarFill: $("todayBarFill"),
    historyList: $("historyList"),
    foodModal: $("foodModal"), foodSearch: $("foodSearch"), foodList: $("foodList"),
    closeModalBtn: $("closeModalBtn"), canvas: $("canvas"),
  };

  /* ---------------------------------------------------------- 工具 */
  const api = async (url, options = {}) => {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json().catch(() => ({ ok: false, error: "返回内容无法解析" }));
    if (!res.ok || data.ok === false) throw new Error(data.error || `请求失败 (${res.status})`);
    return data;
  };

  const setStatus = (text) => { els.statusText.textContent = text || ""; };

  const computeItem = (base, grams) => {
    const g = Math.max(1, Math.round(grams));
    const k = g / 100;
    return {
      ...base,
      grams: g,
      kcal: Math.round(base.kcal_per_100 * k),
      protein: +(base.protein_per_100 * k).toFixed(1),
      fat: +(base.fat_per_100 * k).toFixed(1),
      carb: +(base.carb_per_100 * k).toFixed(1),
    };
  };

  const totals = () => state.items.reduce(
    (acc, i) => {
      acc.kcal += i.kcal; acc.protein += i.protein; acc.fat += i.fat; acc.carb += i.carb;
      return acc;
    },
    { kcal: 0, protein: 0, fat: 0, carb: 0 }
  );

  /* ---------------------------------------------------------- 图片处理 */
  const compress = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("读取图片失败"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("图片格式无法识别"));
      img.onload = () => {
        const MAX = 1280;
        const scale = Math.min(1, MAX / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale);
        const h = Math.round(img.height * scale);
        const cv = els.canvas;
        cv.width = w; cv.height = h;
        const ctx = cv.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);
        resolve(cv.toDataURL("image/jpeg", 0.82));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });

  const showImage = (dataUrl) => {
    state.image = dataUrl;
    els.preview.src = dataUrl;
    els.previewWrap.hidden = false;
    els.dropZone.hidden = true;
    els.analyzeBtn.disabled = false;
    els.resultHint.textContent = "已就绪";
    setStatus("图片已就绪，点击「开始识别」。");
  };

  const clearAll = () => {
    state.image = null; state.items = []; state.saved = false; state.advice = "";
    els.preview.src = ""; els.previewWrap.hidden = true; els.dropZone.hidden = false;
    els.analyzeBtn.disabled = true;
    els.resultBody.hidden = true; els.emptyState.hidden = false;
    els.advice.hidden = true;
    els.resultHint.textContent = "等待图片";
    els.fileInput.value = "";
    setStatus("选择一张照片后即可开始分析。");
  };

  /* ---------------------------------------------------------- 取图事件 */
  els.dropZone.addEventListener("click", () => els.fileInput.click());
  els.dropZone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.fileInput.click(); }
  });
  ["dragenter", "dragover"].forEach((ev) =>
    els.dropZone.addEventListener(ev, (e) => { e.preventDefault(); els.dropZone.classList.add("drag"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    els.dropZone.addEventListener(ev, (e) => { e.preventDefault(); els.dropZone.classList.remove("drag"); })
  );
  els.dropZone.addEventListener("drop", async (e) => {
    const file = e.dataTransfer?.files?.[0];
    if (file) await handleFile(file);
  });
  els.fileInput.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (file) await handleFile(file);
  });

  async function handleFile(file) {
    if (!file.type.startsWith("image/")) { setStatus("请选择图片文件。"); return; }
    if (file.size > 25 * 1024 * 1024) { setStatus("图片超过 25MB，请换一张。"); return; }
    try {
      setStatus("正在处理图片…");
      showImage(await compress(file));
    } catch (err) {
      setStatus(err.message);
    }
  }

  els.clearBtn.addEventListener("click", clearAll);

  /* ---------------------------------------------------------- 摄像头 */
  els.cameraBtn.addEventListener("click", async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("当前环境不支持摄像头，请改用上传图片。");
      return;
    }
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
        audio: false,
      });
      els.video.srcObject = state.stream;
      els.cameraBox.hidden = false;
      els.dropZone.hidden = true;
      els.previewWrap.hidden = true;
      setStatus("取景后点击「拍摄这张」。");
    } catch (err) {
      setStatus("无法打开摄像头：" + (err.message || "权限被拒绝") + "，可改用上传图片。");
    }
  });

  const stopCamera = () => {
    if (state.stream) {
      state.stream.getTracks().forEach((t) => t.stop());
      state.stream = null;
    }
    els.video.srcObject = null;
    els.cameraBox.hidden = true;
    els.dropZone.hidden = !!state.image;
    els.previewWrap.hidden = !state.image;
  };
  els.closeCamBtn.addEventListener("click", stopCamera);

  els.snapBtn.addEventListener("click", () => {
    const v = els.video;
    if (!v.videoWidth) { setStatus("摄像头尚未就绪，稍等一秒再试。"); return; }
    const MAX = 1280;
    const scale = Math.min(1, MAX / Math.max(v.videoWidth, v.videoHeight));
    const cv = els.canvas;
    cv.width = Math.round(v.videoWidth * scale);
    cv.height = Math.round(v.videoHeight * scale);
    cv.getContext("2d").drawImage(v, 0, 0, cv.width, cv.height);
    const dataUrl = cv.toDataURL("image/jpeg", 0.82);
    stopCamera();
    showImage(dataUrl);
  });

  /* ---------------------------------------------------------- 分析 */
  els.analyzeBtn.addEventListener("click", async () => {
    if (!state.image) return;
    stopCamera();
    els.analyzeBtn.classList.add("loading");
    els.analyzeBtn.disabled = true;
    setStatus(state.mode === "mock"
      ? "正在分析（演示模式，结果由本地模拟生成）…"
      : "正在调用视觉模型识别，通常需要 3–10 秒…");
    try {
      const data = await api("/api/analyze", {
        method: "POST",
        body: JSON.stringify({ image: state.image }),
      });
      state.items = data.items.map((i) => ({ ...i }));
      state.mode = data.mode || "mock";
      state.advice = data.advice || "";
      state.saved = false;

      els.emptyState.hidden = true;
      els.resultBody.hidden = false;
      els.resultHint.textContent = data.mode === "mock" ? "演示数据" : "识别完成";
      els.notice.hidden = !data.note && !data.warning;
      els.notice.textContent = [data.note, data.warning].filter(Boolean).join(" ");

      els.advice.hidden = !state.advice;
      els.advice.textContent = state.advice ? "建议：" + state.advice : "";

      render();
      setStatus(data.mode === "mock"
        ? "演示模式完成。调整克重可实时重算热量。"
        : "识别完成，可微调份量后保存。");
    } catch (err) {
      setStatus("识别失败：" + err.message);
    } finally {
      els.analyzeBtn.classList.remove("loading");
      els.analyzeBtn.disabled = !state.image;
    }
  });

  /* ---------------------------------------------------------- 渲染 */
  function render() {
    renderItems();
    renderTotals();
  }

  function renderItems() {
    els.itemCount.textContent = state.items.length;
    els.items.innerHTML = state.items.map((item, idx) => `
      <div class="item" data-idx="${idx}">
        <div class="item-top">
          <div class="item-name">
            ${escapeHtml(item.name)}
            <span class="tag ${item.source === "模型估算" ? "est" : "lib"}">${item.source === "模型估算" ? "估算" : "营养库"}</span>
            <span class="tag conf">${Math.round((item.confidence || 0.8) * 100)}%</span>
          </div>
          <div class="item-kcal">${item.kcal}<small>kcal</small></div>
        </div>
        <div class="item-meta">
          ${item.kcal_per_100} kcal/100g · 蛋白 ${item.protein_per_100}g · 脂肪 ${item.fat_per_100}g · 碳水 ${item.carb_per_100}g
        </div>
        <div class="gram-row">
          <button class="gram-btn" data-act="minus" data-idx="${idx}" aria-label="减少份量">−</button>
          <input type="range" min="10" max="${Math.max(800, item.grams)}" step="5" value="${item.grams}" data-act="range" data-idx="${idx}">
          <button class="gram-btn" data-act="plus" data-idx="${idx}" aria-label="增加份量">＋</button>
          <span class="gram-val">${item.grams} g</span>
          <button class="del-btn" data-act="del" data-idx="${idx}">删除</button>
        </div>
      </div>
    `).join("");
  }

  els.items.addEventListener("input", (e) => {
    const t = e.target;
    if (t.dataset.act !== "range") return;
    const idx = +t.dataset.idx;
    const item = state.items[idx];
    if (!item) return;
    state.items[idx] = computeItem(item, +t.value);
    updateItemDom(idx);
    renderTotals();
  });

  function updateItemDom(idx) {
    const card = els.items.querySelector(`.item[data-idx="${idx}"]`);
    const item = state.items[idx];
    if (!card || !item) return;
    card.querySelector(".item-kcal").innerHTML = `${item.kcal}<small>kcal</small>`;
    card.querySelector(".gram-val").textContent = `${item.grams} g`;
  }

  els.items.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "range") return;
    const idx = +btn.dataset.idx;
    const item = state.items[idx];
    if (!item) return;
    if (act === "minus") state.items[idx] = computeItem(item, item.grams - 10);
    else if (act === "plus") state.items[idx] = computeItem(item, item.grams + 10);
    else if (act === "del") state.items.splice(idx, 1);
    if (!state.items.length) { els.resultBody.hidden = true; els.emptyState.hidden = false; }
    render();
  });

  function renderTotals() {
    const t = totals();
    els.totalKcal.textContent = t.kcal;
    els.totalP.textContent = t.protein.toFixed(1) + " g";
    els.totalF.textContent = t.fat.toFixed(1) + " g";
    els.totalC.textContent = t.carb.toFixed(1) + " g";

    const pct = Math.min(t.kcal / DAILY_GOAL, 1);
    els.ringFill.style.strokeDashoffset = String(RING_CIRC * (1 - pct));
    els.ringFill.style.stroke = pct > 0.85 ? "var(--orange)" : "var(--green)";
    els.ringPct.textContent = Math.round(pct * 100) + "%";

    const pe = t.protein * 4, fe = t.fat * 9, ce = t.carb * 4;
    const sum = pe + fe + ce || 1;
    els.stackP.style.width = (pe / sum * 100).toFixed(1) + "%";
    els.stackF.style.width = (fe / sum * 100).toFixed(1) + "%";
    els.stackC.style.width = (ce / sum * 100).toFixed(1) + "%";
  }

  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

  /* ---------------------------------------------------------- 保存 / 重置 */
  els.saveBtn.addEventListener("click", async () => {
    if (!state.items.length) return;
    if (state.saved) { setStatus("这一餐已经保存过了。"); return; }
    els.saveBtn.classList.add("loading");
    try {
      const data = await api("/api/records", {
        method: "POST",
        body: JSON.stringify({ items: state.items, mode: state.mode }),
      });
      state.saved = true;
      renderToday(data.today);
      renderHistory(data.records);
      setStatus("已保存到本机记录。");
    } catch (err) {
      setStatus("保存失败：" + err.message);
    } finally {
      els.saveBtn.classList.remove("loading");
    }
  });

  els.resetBtn.addEventListener("click", clearAll);

  /* ---------------------------------------------------------- 历史 */
  function renderToday(today) {
    els.todayKcal.textContent = today.kcal;
    els.todayCount.textContent = today.count;
    els.todayBarFill.style.width = Math.min(today.kcal / DAILY_GOAL, 1) * 100 + "%";
  }

  function renderHistory(records) {
    if (!records || !records.length) {
      els.historyList.innerHTML = '<p class="no-record">还没有记录，保存一餐后会出现在这里。</p>';
      return;
    }
    els.historyList.innerHTML = records.map((r) => {
      const names = (r.items || []).map((i) => `${i.name} ${i.grams}g`).join("、");
      const time = (r.created_at || "").slice(11, 16);
      return `
        <div class="record">
          <div>
            <div class="record-time">${r.created_at.slice(5, 10)} ${time}</div>
            <p class="record-names">${escapeHtml(names.length > 46 ? names.slice(0, 46) + "…" : names)}</p>
          </div>
          <div style="text-align:right">
            <div class="record-kcal">${Math.round(r.kcal)}<small>kcal</small></div>
            <button class="del-btn" data-rid="${r.id}">删除</button>
          </div>
        </div>`;
    }).join("");
  }

  els.historyList.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-rid]");
    if (!btn) return;
    try {
      const data = await api("/api/records?id=" + btn.dataset.rid, { method: "DELETE" });
      renderToday(data.today);
      renderHistory(data.records);
    } catch (err) {
      setStatus("删除失败：" + err.message);
    }
  });

  /* ---------------------------------------------------------- 手动添加 */
  const openModal = async () => {
    els.foodModal.hidden = false;
    els.foodSearch.value = "";
    await loadFoods("");
    els.foodSearch.focus();
  };
  els.addFoodBtn.addEventListener("click", openModal);
  els.closeModalBtn.addEventListener("click", () => { els.foodModal.hidden = true; });
  els.foodModal.addEventListener("click", (e) => {
    if (e.target === els.foodModal) els.foodModal.hidden = true;
  });

  let searchTimer = null;
  els.foodSearch.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadFoods(els.foodSearch.value), 180);
  });

  async function loadFoods(q) {
    try {
      const data = await api("/api/foods?q=" + encodeURIComponent(q));
      els.foodList.innerHTML = data.foods.map((f) => `
        <div class="food-row" data-name="${escapeHtml(f.name)}">
          <div>
            <div class="fn">${escapeHtml(f.name)}</div>
            <div class="fc">常见份量 ${f.typical}g · ${f.category}</div>
          </div>
          <div class="fk">${f.kcal} kcal/100g</div>
        </div>
      `).join("") || '<p class="no-record">没有匹配的食物。</p>';
      els.foodList.querySelectorAll(".food-row").forEach((row) => {
        row.addEventListener("click", () => {
          const f = data.foods.find((x) => x.name === row.dataset.name);
          if (!f) return;
          const base = {
            name: f.name,
            category: f.category,
            kcal_per_100: f.kcal,
            protein_per_100: f.protein,
            fat_per_100: f.fat,
            carb_per_100: f.carb,
            confidence: 1,
            source: "营养库",
          };
          state.items.push(computeItem(base, f.typical));
          els.foodModal.hidden = true;
          els.emptyState.hidden = true;
          els.resultBody.hidden = false;
          els.resultHint.textContent = "手动添加";
          render();
          setStatus(`已添加「${f.name}」。`);
        });
      });
    } catch (err) {
      els.foodList.innerHTML = `<p class="no-record">加载失败：${escapeHtml(err.message)}</p>`;
    }
  }

  /* ---------------------------------------------------------- 初始化 */
  async function init() {
    try {
      const s = await api("/api/state");
      state.mode = s.mode;
      const isMock = s.mode === "mock";
      els.engineBadge.textContent = isMock
        ? "演示模式 · 无需 Key"
        : `真实识别 · ${s.mode === "qwen" ? "Qwen-VL" : "OpenAI 兼容"}`;
      els.engineBadge.className = "engine-badge " + (isMock ? "demo" : "real");
      if (s.warning) {
        els.notice.hidden = false;
        els.notice.textContent = s.warning;
      }
      renderToday(s.today);
      renderHistory(s.records);
    } catch (err) {
      els.engineBadge.textContent = "服务未连接";
      els.engineBadge.className = "engine-badge demo";
      els.notice.hidden = false;
      els.notice.textContent = "无法连接后端服务：" + err.message;
    }
  }

  clearAll();
  init();
})();
