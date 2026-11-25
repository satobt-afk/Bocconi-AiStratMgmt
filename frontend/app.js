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
  const [status, expenses] = await Promise.all([
    api(`/api/status?month=${currentMonth}`),
    api(`/api/expenses?month=${currentMonth}`),
  ]);

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
      }),
    });
  } catch (err) {
    return showFormError(err.message);
  }

  const s = CATEGORY_STYLE[selectedCategory];
  resetForm();
  currentMonth = todayISO().slice(0, 7);
  showToast(`✅ ${euro(amount)} saved in ${s.emoji} ${s.label}`);
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
  renderChips();
}

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

// ---------- Navigation and toast ----------

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${name}`));
  document.querySelectorAll(".tabbar button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  window.scrollTo(0, 0);
  if (name === "home") renderHome().catch((err) => showToast(err.message));
  if (name === "budgets") renderBudgets().catch((err) => showToast(err.message));
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
