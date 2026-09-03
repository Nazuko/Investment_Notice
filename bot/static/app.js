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

loadQuotes();
