// Frontend for the student budget app.
// It only talks to the backend through the /api/... endpoints:
// all calculations (totals, remaining, over budget) are done in Python.

// Presentation only: one emoji and one color per category, defined in one place.
const CATEGORY_STYLE = {
  rent:       { emoji: "🏠", label: "Rent",       color: "#7f77dd", soft: "#eeedfe" },
  groceries:  { emoji: "🛒", label: "Groceries",  color: "#639922", soft: "#eaf3de" },
  restaurant: { emoji: "🍝", label: "Restaurant", color: "#d85a30", soft: "#faece7" },
  transport:  { emoji: "🚌", label: "Transport",  color: "#378add", soft: "#e6f1fb" },
  leisure:    { emoji: "🎉", label: "Leisure",    color: "#d4537e", soft: "#fbeaf0" },
  travel:     { emoji: "✈️", label: "Travel",     color: "#1d9e75", soft: "#e1f5ee" },
  other:      { emoji: "📦", label: "Other",      color: "#888780", soft: "#f1efe8" },
};

const $ = (id) => document.getElementById(id);
const euro = (n) => `${Number.isInteger(n) ? n : n.toFixed(2)} €`;
const todayISO = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time

let currentMonth = todayISO().slice(0, 7);
let selectedCategory = null;

// ---------- API calls ----------

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    // FastAPI sends either a message string or a list of field errors.
    const detail = Array.isArray(body.detail) ? "Please fill in every required field." : body.detail;
    throw new Error(detail || "Something went wrong");
  }
  return body;
}

// ---------- Home ----------

function shiftMonth(month, delta) {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthName(month) {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

async function renderHome() {
  const isCurrentMonth = currentMonth === todayISO().slice(0, 7);
  const [status, expenses, daily, tipData] = await Promise.all([
    api(`/api/status?month=${currentMonth}`),
    api(`/api/expenses?month=${currentMonth}`),
    api(`/api/daily?month=${currentMonth}`),
    isCurrentMonth ? api("/api/tips") : Promise.resolve({ tips: [] }),
  ]);
  renderTips(tipData.tips);
  const tipCategories = new Set(tipData.tips.map((t) => t.category));
  drawDonut(status);
  drawPace(daily);

  $("month-label").textContent = monthName(currentMonth);
  $("subtitle").textContent =
    status.days_left > 0 ? `${status.days_left} day${status.days_left > 1 ? "s" : ""} left this month` : "Month closed";

  // Budget ring
  const pct = status.total_budget > 0 ? Math.round((status.spent / status.total_budget) * 100) : 0;
  $("ring").style.setProperty("--pct", Math.min(pct, 100));
  $("ring").style.setProperty("--ring-color", pct > 100 ? "#c0392b" : pct >= 85 ? "#ef9f27" : "#7f77dd");
  $("ring-pct").textContent = `${pct}%`;
  $("remaining").textContent = euro(status.remaining);
  $("hero-detail").textContent = `spent ${euro(status.spent)} of ${euro(status.total_budget)}`;

  // Alerts: categories over budget (red) or nearly used up (orange).
  // Exactly on budget (e.g. rent paid) is normal, so it gets no alert.
  const entries = Object.entries(status.categories);
  const nearlyUsed = (c) => c.budget > 0 && c.remaining > 0 && c.spent / c.budget >= 0.85;
  $("alerts").innerHTML = entries
    .filter(([name, c]) => !tipCategories.has(name)) // a tip card already covers it
    .filter(([, c]) => c.over_budget || nearlyUsed(c))
    .map(([name, c]) => {
      const s = CATEGORY_STYLE[name];
      return c.over_budget
        ? `<div class="alert over">⚠️ <b>${s.label}</b>: ${euro(c.spent)} spent for a ${euro(c.budget)} budget (${euro(-c.remaining)} over).</div>`
        : `<div class="alert">👀 <b>${s.label}</b>: only ${euro(c.remaining)} left in this category.</div>`;
    })
    .join("");

  // Category cards
  $("categories").innerHTML = entries.length
    ? entries.map(([name, c]) => categoryCard(name, c)).join("")
    : `<div class="card empty">No budget yet. Set one in 🎯 Budgets.</div>`;

  // Latest expenses (newest first)
  const latest = expenses.slice().reverse().slice(0, 8);
  $("expenses").innerHTML = latest.length
    ? latest.map(expenseRow).join("")
    : `<li class="empty">No expenses this month yet. Tap ➕ to add one.</li>`;
}

function categoryCard(name, c) {
  const s = CATEGORY_STYLE[name];
  const pct = c.budget > 0 ? Math.min(100, Math.round((c.spent / c.budget) * 100)) : 100;
  const barColor = c.over_budget ? "#c0392b" : s.color;
  return `
    <div class="card cat">
      <div class="bubble" style="background:${s.soft}">${s.emoji}</div>
      <div class="cat-body">
        <div class="cat-top">
          <span>${s.label}</span>
          <span class="${c.over_budget ? "over" : ""}">${euro(c.spent)} / ${euro(c.budget)}</span>
        </div>
        <div class="bar"><i style="width:${pct}%;background:${barColor}"></i></div>
      </div>
    </div>`;
}

function expenseRow(e) {
  const s = CATEGORY_STYLE[e.category];
  const day = new Date(e.date + "T00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const merchant = e.merchant ? escapeHtml(e.merchant) : s.label;
  const tag = e.source === "synthetic" ? `<span class="tag">demo data</span>` : "";
  return `
    <li>
      <div class="bubble" style="background:${s.soft}">${s.emoji}</div>
      <div class="what">${merchant}${tag}<small>${day} · ${s.label}</small></div>
      <div class="amt">−${euro(e.amount)}</div>
    </li>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// ---------- Add expense ----------

function renderChips() {
  $("category-chips").innerHTML = Object.entries(CATEGORY_STYLE)
    .map(([name, s]) => {
      const selected = name === selectedCategory;
      const style = selected ? `style="background:${s.soft};color:${s.color}"` : "";
      return `<button type="button" class="chip ${selected ? "selected" : ""}" data-category="${name}" ${style}>${s.emoji} ${s.label}</button>`;
    })
    .join("");
}

$("category-chips").addEventListener("click", (event) => {
  const chip = event.target.closest("[data-category]");
  if (!chip) return;
  selectedCategory = chip.dataset.category;
  $("form-error").hidden = true;
  renderChips();
});

$("expense-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const amount = parseFloat($("amount").value);
  const error = !(amount > 0)
    ? "Enter an amount greater than 0."
    : !selectedCategory
    ? "Pick a category."
    : !$("date").value
    ? "Pick a date."
    : null;
  if (error) return showFormError(error);

  try {
    await api("/api/expenses", {
      method: "POST",
      body: JSON.stringify({
        amount,
        category: selectedCategory,
        date: $("date").value,
        merchant: $("merchant").value.trim(),
        source: expenseSource,
      }),
    });
  } catch (err) {
    return showFormError(err.message);
  }

  const s = CATEGORY_STYLE[selectedCategory];
  const icon = expenseSource === "receipt" ? "📸" : "✅";
  resetForm();
  currentMonth = todayISO().slice(0, 7);
  showToast(`${icon} ${euro(amount)} saved in ${s.emoji} ${s.label}`);
  showView("home");
});

["amount", "date"].forEach((id) => $(id).addEventListener("input", () => ($("form-error").hidden = true)));

function showFormError(message) {
  $("form-error").textContent = message;
  $("form-error").hidden = false;
}

function resetForm() {
  $("expense-form").reset();
  $("date").value = todayISO();
  selectedCategory = null;
  expenseSource = "manual";
  $("scan-status").hidden = true;
  renderChips();
}

// ---------- Receipt scan (vision model + human confirmation) ----------

let expenseSource = "manual"; // becomes "receipt" when the form was filled from a photo

// Shrink the photo and draw it on white: smaller uploads, faster reading, and no
// transparent background (a transparent PNG looked "entirely black" to the model).
// 960 px: on an M1 with 8 GB, a new receipt takes ~15 s instead of ~25 s at 1280 px, with the same result.
function photoToJpeg(file, maxSide = 960) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(img.src);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => reject(new Error("This file is not a photo we can read."));
    img.src = URL.createObjectURL(file);
  });
}

function showScanStatus(kind, html, thumbnail) {
  const box = $("scan-status");
  box.className = `scan-status ${kind}`;
  box.innerHTML = (thumbnail ? `<img src="${thumbnail}" alt="Receipt photo" />` : "") + `<div>${html}</div>`;
  box.hidden = false;
}

$("receipt-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  event.target.value = ""; // allow picking the same photo again
  if (!file) return;

  let photo;
  try {
    photo = await photoToJpeg(file);
  } catch (err) {
    return showScanStatus("error", escapeHtml(err.message));
  }

  const started = Date.now();
  showScanStatus("reading", "🔍 Reading your receipt…", photo);
  const timer = setInterval(() => {
    showScanStatus("reading", `🔍 Reading your receipt… ${Math.round((Date.now() - started) / 1000)}s`, photo);
  }, 1000);

  try {
    const p = await api("/api/receipts/scan", { method: "POST", body: JSON.stringify({ image: photo }) });
    clearInterval(timer);
    // Pre-fill the form: nothing is saved until the student taps "Save".
    $("amount").value = p.amount ?? "";
    $("date").value = p.date;
    $("merchant").value = p.merchant;
    selectedCategory = p.category;
    expenseSource = "receipt";
    renderChips();
    $("form-error").hidden = true;
    const warnings = p.warnings.length
      ? `<ul>${p.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`
      : "";
    showScanStatus("done", `✨ Read by AI. <b>Check the details below</b>, then save.${warnings}`, photo);
  } catch (err) {
    clearInterval(timer);
    showScanStatus("error", escapeHtml(err.message), photo);
  }
});

// ---------- Budgets ----------

async function renderBudgets() {
  const budgets = await api("/api/budgets");
  $("budget-list").innerHTML = Object.entries(CATEGORY_STYLE)
    .map(([name, s]) => `
      <div class="budget-row">
        <div class="bubble" style="background:${s.soft}">${s.emoji}</div>
        <span class="name">${s.label}</span>
        <input type="number" inputmode="decimal" min="0" step="1" value="${budgets[name]}" data-budget="${name}" aria-label="${s.label} budget in euros" />
      </div>`)
    .join("");
  updateBudgetTotal();
}

function updateBudgetTotal() {
  const total = [...document.querySelectorAll("[data-budget]")].reduce((sum, input) => sum + (parseFloat(input.value) || 0), 0);
  $("budget-total").textContent = euro(Math.round(total * 100) / 100);
}

$("budget-list").addEventListener("input", updateBudgetTotal);
$("budget-list").addEventListener("change", async (event) => {
  const input = event.target.closest("[data-budget]");
  if (!input) return;
  const amount = parseFloat(input.value);
  if (!(amount >= 0)) {
    input.value = 0;
    return showToast("Budget must be 0 or more");
  }
  try {
    await api(`/api/budgets/${input.dataset.budget}`, { method: "PUT", body: JSON.stringify({ amount }) });
    showToast(`🎯 ${CATEGORY_STYLE[input.dataset.budget].label} budget saved`);
  } catch (err) {
    showToast(err.message);
  }
});

// ---------- Coach (AI agent) ----------

// Friendly labels for the tools the agent used, so the student sees it worked on real data.
const TOOL_LABELS = {
  get_budget_status: () => "📊 checked your budget",
  forecast_month_end: () => "🔮 forecast your month end",
  get_recent_expenses: () => "🧾 looked at recent expenses",
  get_saving_tips: () => "💡 checked where you can save",
  can_afford: (a) => `🧮 checked ${a.amount ?? "?"} € in ${CATEGORY_STYLE[a.category]?.label ?? a.category}`,
};

const chatHistory = []; // kept in the browser only, sent with each question

function addMessage(role, text, extraClass = "") {
  const div = document.createElement("div");
  div.className = `msg ${role} ${extraClass}`.trim();
  div.textContent = text;
  $("chat").appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
  return div;
}

function addToolChips(tools) {
  if (!tools.length) return;
  const div = document.createElement("div");
  div.className = "tools";
  tools.forEach((t) => {
    const chip = document.createElement("span");
    chip.textContent = (TOOL_LABELS[t.name] || (() => `🔧 ${t.name}`))(t.arguments || {});
    div.appendChild(chip);
  });
  $("chat").appendChild(div);
}

async function askCoach(question) {
  question = question.trim();
  if (!question) return;
  $("suggestions").hidden = true;
  $("chat-input").value = "";
  $("chat-input").disabled = $("chat-form").querySelector("button").disabled = true;
  addMessage("user", question);

  // A local model takes several seconds: show that it is working.
  const thinking = addMessage("bot", "Thinking…", "thinking");
  const started = Date.now();
  const timer = setInterval(() => {
    thinking.textContent = `Thinking… ${Math.round((Date.now() - started) / 1000)}s`;
  }, 1000);

  try {
    const result = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: question, history: chatHistory }),
    });
    thinking.remove();
    addToolChips(result.tools_used);
    addMessage("bot", result.reply || "Sorry, I have no answer for that.");
    // Python's own verdict, word for word: the model's wording cannot change it.
    (result.facts || []).forEach((fact) => addMessage("bot", `📌 From your data: ${fact}`, "fact"));
    chatHistory.push({ role: "user", content: question }, { role: "assistant", content: result.reply });
  } catch (err) {
    thinking.remove();
    addMessage("bot", err.message, "error");
  } finally {
    clearInterval(timer);
    $("chat-input").disabled = $("chat-form").querySelector("button").disabled = false;
    $("chat-input").focus();
  }
}

$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  askCoach($("chat-input").value);
});

$("suggestions").addEventListener("click", (event) => {
  if (event.target.matches(".chip")) askCoach(event.target.textContent);
});

// ---------- Proactive saving tips ----------

function renderTips(tips) {
  $("tips").innerHTML = tips
    .map((t) => {
      const s = CATEGORY_STYLE[t.category];
      const question = `How can I spend less on ${s.label.toLowerCase()} this month?`;
      return `
        <div class="tip ${t.kind === "over_budget" ? "over" : ""}">
          <div class="tip-head"><span class="bubble" style="background:${s.soft}">${s.emoji}</span><b>💡 Tip</b></div>
          <p>${escapeHtml(t.message)}</p>
          ${t.insight ? `<p class="tip-insight">🔍 ${escapeHtml(t.insight)}</p>` : ""}
          <p class="tip-action">👉 ${escapeHtml(t.tip)}</p>
          <button type="button" class="tip-ask" data-question="${escapeHtml(question)}">🤖 Ask the coach</button>
        </div>`;
    })
    .join("");
}

$("tips").addEventListener("click", (event) => {
  const button = event.target.closest("[data-question]");
  if (!button) return;
  showView("coach");
  askCoach(button.dataset.question);
});

// ---------- Charts (plain SVG: no library, works offline) ----------
// The numbers come from the API; the browser only draws them.

function drawDonut(status) {
  const slices = Object.entries(status.categories).filter(([, c]) => c.spent > 0);
  if (!slices.length) {
    $("donut").innerHTML = "";
    $("donut-legend").innerHTML = `<li class="empty">No spending yet this month.</li>`;
    return;
  }
  const r = 46, circumference = 2 * Math.PI * r;
  let offset = 0;
  const arcs = slices.map(([name, c]) => {
    const length = (c.spent / status.spent) * circumference;
    const arc = `<circle cx="60" cy="60" r="${r}" fill="none" stroke="${CATEGORY_STYLE[name].color}" stroke-width="18"
      stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" transform="rotate(-90 60 60)"/>`;
    offset += length;
    return arc;
  });
  $("donut").innerHTML = `<svg viewBox="0 0 120 120" role="img" aria-label="Spending by category">
    ${arcs.join("")}
    <text x="60" y="57" text-anchor="middle" font-size="16" font-weight="700" fill="currentColor">${euro(Math.round(status.spent))}</text>
    <text x="60" y="73" text-anchor="middle" font-size="9" fill="#6b6a65">spent</text></svg>`;
  $("donut-legend").innerHTML = slices
    .sort(([, a], [, b]) => b.spent - a.spent)
    .map(([name, c]) => {
      const s = CATEGORY_STYLE[name];
      const pct = Math.round((c.spent / status.spent) * 100);
      return `<li><span class="dot" style="background:${s.color}"></span><span class="name">${s.emoji} ${s.label}</span><span class="pct">${pct}%</span></li>`;
    })
    .join("");
}

function drawPace(daily) {
  const W = 320, H = 170, left = 34, right = 8, top = 10, bottom = 22;
  const days = daily.days;
  const max = Math.max(1, daily.total_budget, ...days.map((d) => d.cumulative || 0));
  const x = (i) => left + (i / (days.length - 1)) * (W - left - right);
  const y = (v) => top + (1 - v / max) * (H - top - bottom);
  const line = (key) => days.filter((d) => d[key] !== null).map((d, i) => `${x(i).toFixed(1)},${y(d[key]).toFixed(1)}`).join(" ");

  const known = days.filter((d) => d.cumulative !== null);
  const last = known[known.length - 1];
  const lastIndex = known.length - 1;
  const ticks = [0, Math.round(max / 2), Math.round(max)];
  $("pace-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Spending day by day against the ideal pace">
    ${ticks.map((t) => `<line x1="${left}" x2="${W - right}" y1="${y(t)}" y2="${y(t)}" stroke="#ebe8e1"/>
      <text x="${left - 4}" y="${y(t) + 3}" text-anchor="end" font-size="9" fill="#6b6a65">${t}€</text>`).join("")}
    <text x="${left}" y="${H - 6}" font-size="9" fill="#6b6a65">1</text>
    <text x="${W - right}" y="${H - 6}" text-anchor="end" font-size="9" fill="#6b6a65">${days.length}</text>
    <polyline points="${line("ideal")}" fill="none" stroke="#7f77dd" stroke-width="2" stroke-dasharray="5 4"/>
    ${known.length ? `<polyline points="${line("cumulative")}" fill="none" stroke="#d4537e" stroke-width="3" stroke-linejoin="round"/>
      <circle cx="${x(lastIndex)}" cy="${y(last.cumulative)}" r="4.5" fill="#d4537e"/>` : ""}
  </svg>`;

  if (!last) {
    $("pace-caption").innerHTML = `<span style="color:#7f77dd">- - ideal pace</span>. This month has not started yet.`;
    return;
  }
  const gap = Math.round(last.cumulative - last.ideal);
  const status = gap > 0
    ? `You are <b>${euro(gap)} above</b> the ideal pace 🐢 slow down a little.`
    : `You are <b>${euro(-gap)} below</b> the ideal pace 🎉 well done.`;
  $("pace-caption").innerHTML =
    `<span style="color:#d4537e">━ you</span> · <span style="color:#7f77dd">- - ideal pace</span> (rent on day 1, the rest spread evenly).<br>${status}`;
}

// ---------- Year ----------

let currentYear = new Date().getFullYear();

async function renderYear() {
  const data = await api(`/api/year?year=${currentYear}`);
  $("year-label").textContent = data.year;
  const months = data.months;
  const active = months.filter((m) => m.spent > 0);
  const total = active.reduce((sum, m) => sum + m.spent, 0);
  $("year-total").textContent = euro(Math.round(total));
  $("year-average").textContent = active.length ? euro(Math.round(total / active.length)) : "–";
  $("year-over").textContent = months.filter((m) => m.budget > 0 && m.spent > m.budget).length;

  const W = 320, H = 180, left = 4, right = 4, top = 16, bottom = 20;
  const max = Math.max(1, ...months.map((m) => Math.max(m.spent, m.budget)));
  const slot = (W - left - right) / 12;
  const y = (v) => top + (1 - v / max) * (H - top - bottom);
  const bars = months.map((m, i) => {
    const bx = left + i * slot + slot * 0.18, bw = slot * 0.64;
    const color = m.spent === 0 ? "#ebe8e1" : m.budget > 0 && m.spent > m.budget ? "#c0392b" : "#7f77dd";
    const by = y(m.spent);
    const label = new Date(data.year, i, 1).toLocaleDateString("en-GB", { month: "short" }).slice(0, 1);
    return `<g class="bar-hit" data-month="${m.month}">
      <rect x="${left + i * slot}" y="${top}" width="${slot}" height="${H - top - bottom}" fill="transparent"/>
      <rect x="${bx}" y="${m.spent ? by : H - bottom - 2}" width="${bw}" height="${m.spent ? H - bottom - by : 2}" rx="3" fill="${color}"/>
      ${m.spent ? `<text x="${bx + bw / 2}" y="${by - 4}" text-anchor="middle" font-size="8" fill="#6b6a65">${Math.round(m.spent)}</text>` : ""}
      <text x="${bx + bw / 2}" y="${H - 6}" text-anchor="middle" font-size="10" fill="#6b6a65">${label}</text></g>`;
  });
  const budget = months[0].budget;
  $("year-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Spending month by month">
    ${bars.join("")}
    ${budget > 0 ? `<line x1="${left}" x2="${W - right}" y1="${y(budget)}" y2="${y(budget)}" stroke="#2c2c2a" stroke-dasharray="4 4" opacity="0.6"/>` : ""}
  </svg>`;
}

$("year-chart").addEventListener("click", (event) => {
  const bar = event.target.closest("[data-month]");
  if (!bar) return;
  currentMonth = bar.dataset.month;
  showView("home");
});
$("prev-year").addEventListener("click", () => {
  currentYear -= 1;
  renderYear();
});
$("next-year").addEventListener("click", () => {
  currentYear += 1;
  renderYear();
});

// ---------- Navigation and toast ----------

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${name}`));
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  window.scrollTo(0, 0);
  if (name === "home") renderHome().catch((err) => showToast(err.message));
  if (name === "budgets") renderBudgets().catch((err) => showToast(err.message));
  if (name === "year") renderYear().catch((err) => showToast(err.message));
}

document.querySelector(".tabbar").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (button) showView(button.dataset.view);
});

$("prev-month").addEventListener("click", () => {
  currentMonth = shiftMonth(currentMonth, -1);
  renderHome();
});
$("next-month").addEventListener("click", () => {
  currentMonth = shiftMonth(currentMonth, 1);
  renderHome();
});

let toastTimer;
function showToast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 2500);
}

// ---------- Start ----------

resetForm();
showView("home");
