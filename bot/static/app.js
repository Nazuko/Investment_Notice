async function loadQuotes() {
  const rows = document.querySelectorAll("[data-symbol]");
  if (!rows.length) return;
  let quotes = {};
  try {
    const res = await fetch("/api/quotes");
    quotes = await res.json();
  } catch (err) {
    quotes = {};
  }
  rows.forEach((row) => {
    const symbol = row.dataset.symbol;
    const price = quotes[symbol];
    const priceCell = row.querySelector(".price");
    const pnlCell = row.querySelector(".pnl");
    if (priceCell) {
      priceCell.textContent = price == null ? "—" : Number(price).toFixed(2);
    }
    if (pnlCell) {
      const cost = Number(row.dataset.avgCost);
      if (price == null || !cost) {
        pnlCell.textContent = "—";
        return;
      }
      const pct = ((price - cost) / cost) * 100;
      pnlCell.textContent = `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
      pnlCell.classList.add(pct >= 0 ? "up" : "down");
    }
  });
}

function bindCombo(root) {
  const query = root.querySelector(".combo-query");
  const yahoo = root.querySelector(".combo-yahoo");
  const list = root.querySelector(".combo-list");
  let items = [];
  let active = -1;
  let timer = null;

  function hide() {
    list.hidden = true;
    list.innerHTML = "";
    active = -1;
  }

  function render() {
    list.innerHTML = "";
    items.forEach((item, idx) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.dataset.yahoo = item.yahoo;
      li.dataset.label = item.label;
      li.textContent = item.label;
      li.setAttribute("aria-selected", idx === active ? "true" : "false");
      li.addEventListener("mousedown", (event) => {
        event.preventDefault();
        choose(item);
      });
      list.appendChild(li);
    });
    list.hidden = items.length === 0;
  }

  function choose(item) {
    yahoo.value = item.yahoo;
    query.value = item.label;
    hide();
  }

  async function lookup(q) {
    const res = await fetch(`/api/symbols?q=${encodeURIComponent(q)}`);
    items = await res.json();
    active = items.length ? 0 : -1;
    render();
  }

  query.addEventListener("input", () => {
    yahoo.value = "";
    clearTimeout(timer);
    timer = setTimeout(() => lookup(query.value), 120);
  });
  query.addEventListener("focus", () => lookup(query.value));
  query.addEventListener("blur", () => setTimeout(hide, 120));
  query.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!items.length) return;
      active = (active + 1) % items.length;
      render();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!items.length) return;
      active = (active - 1 + items.length) % items.length;
      render();
    } else if (event.key === "Enter") {
      if (!list.hidden && items[active]) {
        event.preventDefault();
        choose(items[active]);
      }
    } else if (event.key === "Escape") {
      hide();
    }
  });

  root.closest("form").addEventListener("submit", (event) => {
    if (!yahoo.value) {
      event.preventDefault();
      query.focus();
      lookup(query.value);
    }
  });
}

document.querySelectorAll("[data-combo]").forEach(bindCombo);
loadQuotes();
