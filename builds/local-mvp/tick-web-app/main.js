const CHART_UPDATE_MS = 160;
const HISTORY_POINTS = 260;

const markets = [
  makeMarket({
    symbol: "BTC",
    name: "Bitcoin",
    assetClass: "CRYPTO",
    venue: "Best venue",
    maxLeverage: 100,
    price: 63719.62,
    move: -3.18,
    points: [74, 72, 70, 68, 69, 66, 63, 65, 61, 58, 56, 59, 55, 52, 49, 51, 48, 45, 42, 44, 40, 38, 35, 32, 30, 28, 24, 22],
    accent: "#ff9f2e",
    glow: "#ffbd61",
    themeTop: "#101918",
    themeBottom: "#251c0d",
    volatility: 1.12,
    driftBias: -0.006
  }),
  makeMarket({
    symbol: "SOL",
    name: "Solana",
    assetClass: "CRYPTO",
    venue: "Best venue",
    maxLeverage: 100,
    price: 148.32,
    move: 6.24,
    points: [34, 37, 36, 40, 44, 42, 48, 53, 50, 57, 62, 59, 66, 71, 68, 74, 78, 73, 80, 84, 79, 86, 82, 88, 83, 87, 85, 89],
    accent: "#22d3ee",
    glow: "#67e8f9",
    themeTop: "#07171b",
    themeBottom: "#08333a",
    volatility: 1.28,
    driftBias: 0.014
  }),
  makeMarket({
    symbol: "NVDA",
    name: "Nvidia",
    assetClass: "STOCK",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 182.4,
    move: 4.86,
    points: [28, 30, 29, 33, 38, 36, 41, 45, 49, 47, 53, 57, 54, 60, 64, 62, 68, 72, 69, 75, 78, 73, 80, 84, 81, 85, 82, 86],
    accent: "#5eead4",
    glow: "#8ff5e7",
    themeTop: "#0b171a",
    themeBottom: "#0b3030",
    volatility: 0.96,
    driftBias: 0.012
  }),
  makeMarket({
    symbol: "COIN",
    name: "Coinbase",
    assetClass: "STOCK",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 248.74,
    move: -4.28,
    points: [72, 70, 66, 68, 63, 59, 61, 55, 51, 53, 48, 45, 42, 46, 40, 36, 39, 34, 30, 33, 29, 25, 31, 37, 34, 41, 39, 44],
    accent: "#3b82f6",
    glow: "#93c5fd",
    themeTop: "#0b1421",
    themeBottom: "#102653",
    volatility: 1.16,
    driftBias: -0.01
  }),
  makeMarket({
    symbol: "ETH",
    name: "Ethereum",
    assetClass: "CRYPTO",
    venue: "Best venue",
    maxLeverage: 100,
    price: 1793.6,
    move: 1.41,
    points: [42, 43, 41, 44, 45, 46, 44, 47, 50, 49, 52, 53, 51, 54, 56, 55, 58, 61, 60, 62, 64, 63, 65, 67, 66, 69, 70, 72],
    accent: "#ff9f2e",
    glow: "#ffc66b",
    themeTop: "#121817",
    themeBottom: "#29210d",
    volatility: 0.98,
    driftBias: 0.005
  }),
  makeMarket({
    symbol: "SPY",
    name: "S&P 500 ETF",
    assetClass: "ETF",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 631.22,
    move: 0.78,
    points: [46, 47, 48, 47, 49, 51, 50, 52, 54, 55, 54, 56, 58, 57, 59, 61, 60, 63, 62, 64, 66, 65, 67, 69, 68, 70, 71, 72],
    accent: "#14b8a6",
    glow: "#5eead4",
    themeTop: "#0a1717",
    themeBottom: "#0d3430",
    volatility: 0.58,
    driftBias: 0.005
  }),
  makeMarket({
    symbol: "TSLA",
    name: "Tesla",
    assetClass: "STOCK",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 442.8,
    move: -5.4,
    points: [77, 74, 70, 72, 68, 63, 66, 59, 54, 57, 50, 44, 47, 41, 36, 38, 32, 28, 31, 25, 22, 29, 36, 42, 39, 47, 51, 49],
    accent: "#fb7185",
    glow: "#fda4af",
    themeTop: "#190f14",
    themeBottom: "#321421",
    volatility: 1.22,
    driftBias: -0.01
  }),
  makeMarket({
    symbol: "QQQ",
    name: "Nasdaq ETF",
    assetClass: "ETF",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 562.88,
    move: 2.44,
    points: [35, 37, 36, 39, 42, 41, 45, 49, 48, 52, 55, 53, 58, 60, 59, 63, 66, 64, 68, 71, 69, 74, 72, 76, 78, 77, 80, 79],
    accent: "#84cc16",
    glow: "#bef264",
    themeTop: "#11180b",
    themeBottom: "#26370d",
    volatility: 0.72,
    driftBias: 0.008
  }),
  makeMarket({
    symbol: "US100",
    name: "Nasdaq",
    assetClass: "INDEX",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 26240,
    move: 2.08,
    points: [34, 35, 37, 36, 39, 43, 41, 45, 49, 52, 50, 54, 57, 55, 59, 63, 61, 65, 68, 67, 70, 72, 71, 75, 73, 77, 79, 78],
    accent: "#60a5fa",
    glow: "#93c5fd",
    themeTop: "#0d1521",
    themeBottom: "#102846",
    volatility: 0.76,
    driftBias: 0.008
  }),
  makeMarket({
    symbol: "GLD",
    name: "Gold ETF",
    assetClass: "ETF",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 309.42,
    move: 1.12,
    points: [44, 45, 44, 46, 48, 47, 49, 51, 50, 53, 52, 55, 57, 56, 58, 59, 61, 60, 63, 65, 64, 66, 68, 67, 70, 69, 72, 73],
    accent: "#eab308",
    glow: "#fde047",
    themeTop: "#17150c",
    themeBottom: "#332806",
    volatility: 0.6,
    driftBias: 0.005
  }),
  makeMarket({
    symbol: "XAU",
    name: "Gold",
    assetClass: "COMMODITY",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 4215.3,
    move: 1.26,
    points: [46, 45, 47, 49, 48, 51, 53, 52, 55, 56, 54, 57, 60, 58, 61, 63, 62, 65, 64, 67, 69, 68, 70, 72, 71, 74, 73, 75],
    accent: "#facc15",
    glow: "#fde68a",
    themeTop: "#17150d",
    themeBottom: "#302609",
    volatility: 0.66,
    driftBias: 0.006
  }),
  makeMarket({
    symbol: "WTI",
    name: "Crude Oil",
    assetClass: "COMMODITY",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 58.4,
    move: -3.72,
    points: [62, 59, 55, 58, 53, 50, 52, 48, 43, 45, 39, 35, 38, 34, 30, 32, 28, 25, 29, 33, 31, 36, 41, 39, 44, 46, 43, 48],
    accent: "#f97316",
    glow: "#fdba74",
    themeTop: "#19120c",
    themeBottom: "#331c0a",
    volatility: 1.1,
    driftBias: -0.008
  }),
  makeMarket({
    symbol: "EURUSD",
    name: "Euro Dollar",
    assetClass: "FX",
    venue: "Ostium route",
    maxLeverage: 100,
    price: 1.1684,
    move: 0.42,
    points: [40, 41, 42, 41, 43, 45, 44, 46, 47, 49, 48, 50, 52, 51, 53, 54, 56, 55, 57, 59, 58, 60, 62, 61, 63, 62, 64, 65],
    accent: "#a3e635",
    glow: "#d9f99d",
    themeTop: "#10170d",
    themeBottom: "#20310d",
    volatility: 0.52,
    driftBias: 0.004
  })
];

const state = {
  page: "board",
  focus: false,
  search: "",
  selectedIndex: 0,
  balance: 420.6,
  stake: 25,
  leverage: 100,
  position: null
};

const els = {
  boardScreen: document.getElementById("boardScreen"),
  workspaceScreen: document.getElementById("workspaceScreen"),
  chartGrid: document.getElementById("chartGrid"),
  boardBalance: document.getElementById("boardBalance"),
  workBalance: document.getElementById("workBalance"),
  marketSearch: document.getElementById("marketSearch"),
  backToBoard: document.getElementById("backToBoard"),
  focusToggle: document.getElementById("focusToggle"),
  collapsePanel: document.getElementById("collapsePanel"),
  expandTool: document.getElementById("expandTool"),
  workbench: document.getElementById("workbench"),
  focusDesk: document.getElementById("focusDesk"),
  marketRail: document.getElementById("marketRail"),
  mainChart: document.getElementById("mainChart"),
  focusChart: document.getElementById("focusChart"),
  positionBadge: document.getElementById("positionBadge"),
  marketStats: document.getElementById("marketStats"),
  depthRows: document.getElementById("depthRows"),
  orderActions: document.getElementById("orderActions"),
  stakePresets: document.getElementById("stakePresets"),
  leveragePresets: document.getElementById("leveragePresets")
};

setupBoard();
setupPresets();
bindEvents();
renderAll();

setInterval(() => {
  updateMarkets();
  updatePositionMark();
  renderAll();
}, CHART_UPDATE_MS);

window.addEventListener("resize", () => {
  renderAll();
});

function makeMarket(market) {
  return {
    ...market,
    points: expandPoints(market.points)
  };
}

function expandPoints(points) {
  const output = [];

  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    const steps = 8;

    for (let step = 0; step < steps; step += 1) {
      const progress = step / steps;
      const wave = Math.sin(progress * Math.PI) * 1.3;
      output.push(start + (end - start) * progress + wave * Math.sign(end - start || 1));
    }
  }

  output.push(points[points.length - 1]);

  while (output.length < HISTORY_POINTS) {
    const last = output[output.length - 1] ?? 50;
    output.push(last + Math.sin(output.length / 6) * 0.12);
  }

  return output.slice(-HISTORY_POINTS);
}

function setupBoard() {
  els.chartGrid.innerHTML = markets
    .map(
      (market, index) => `
        <button class="chart-card" data-index="${index}" style="--accent:${market.accent};">
          <div class="card-top">
            <div>
              <div class="card-symbol">${market.symbol}</div>
              <div class="card-name">${market.name}</div>
            </div>
            <div class="card-class">${market.assetClass}</div>
          </div>
          <canvas class="card-canvas" data-chart-index="${index}"></canvas>
          <div class="card-bottom">
            <div class="card-price" data-price-index="${index}">${formatPrice(market.price)}</div>
            <div class="card-move" data-move-index="${index}">${formatPercent(market.move)}</div>
          </div>
        </button>
      `
    )
    .join("");

  document.querySelectorAll(".chart-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.selectedIndex = Number(card.dataset.index);
      state.page = "tool";
      state.focus = false;
      renderAll();
    });
  });
}

function setupPresets() {
  els.stakePresets.innerHTML = [10, 25, 50]
    .map((value) => `<button class="preset-button" data-stake="${value}">$${value}</button>`)
    .join("");
  els.leveragePresets.innerHTML = [25, 50, 100]
    .map((value) => `<button class="preset-button" data-leverage="${value}">${value}x</button>`)
    .join("");

  els.stakePresets.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.stake = Number(button.dataset.stake);
      renderAll();
    });
  });

  els.leveragePresets.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.leverage = Number(button.dataset.leverage);
      renderAll();
    });
  });
}

function bindEvents() {
  els.marketSearch.addEventListener("input", () => {
    state.search = els.marketSearch.value.trim().toLowerCase();
    renderAll();
  });

  els.marketSearch.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const firstMatch = markets.findIndex((market) => marketMatchesSearch(market));
    if (firstMatch === -1) return;
    state.selectedIndex = firstMatch;
    state.page = "tool";
    state.focus = false;
    renderAll();
  });

  els.backToBoard.addEventListener("click", () => {
    state.page = "board";
    state.focus = false;
    renderAll();
  });

  els.focusToggle.addEventListener("click", () => {
    state.focus = !state.focus;
    renderAll();
  });

  els.collapsePanel.addEventListener("click", () => {
    state.focus = true;
    renderAll();
  });

  els.expandTool.addEventListener("click", () => {
    state.focus = false;
    renderAll();
  });

  document.getElementById("focusLong").addEventListener("click", () => openPosition("up"));
  document.getElementById("focusShort").addEventListener("click", () => openPosition("down"));
  document.getElementById("focusClose").addEventListener("click", closePosition);
}

function updateMarkets() {
  const now = Date.now();

  markets.forEach((market, index) => {
    const last = market.points[market.points.length - 1] ?? 50;
    const previous = market.points[market.points.length - 2] ?? last;
    const beforePrevious = market.points[market.points.length - 3] ?? previous;
    const velocity = last - previous;
    const acceleration = previous - beforePrevious;
    const assetRhythm =
      market.assetClass === "FX"
        ? 0.7
        : market.assetClass === "ETF"
          ? 0.74
          : market.assetClass === "INDEX"
            ? 0.82
            : market.assetClass === "STOCK"
              ? 1.1
              : market.assetClass === "COMMODITY"
                ? 1
                : 1.16;
    const volatility = market.volatility * assetRhythm;
    const regimeWave = Math.sin(now / 4300 + index * 1.18);
    const regime = regimeWave > 0 ? 1 : -1;
    const trend = market.driftBias + (market.move >= 0 ? 0.004 : -0.004);
    const fastPulse = Math.sin(now / 190 + index * 1.9) * 0.03 * volatility;
    const midPulse = Math.sin(now / 610 + index * 1.1) * 0.042 * volatility;
    const momentum = clamp(velocity * 0.041 + acceleration * 0.015, -0.06, 0.06) * volatility;
    const edgeReversal = last > 82 ? -0.12 * volatility : last < 18 ? 0.12 * volatility : 0;
    const squeeze = regimeWave > 0.7 ? Math.sign(velocity || regime) * 0.044 * volatility : 0;
    const pullback = Math.random() > 0.9 ? -Math.sign(velocity || regime) * (0.045 + Math.random() * 0.08) * volatility : 0;
    const breakout = Math.random() > 0.965 ? Math.sign(regime + velocity || 1) * (0.14 + Math.random() * 0.2) * volatility : 0;
    const wick = Math.random() > 0.986 ? -Math.sign(velocity || regime) * (0.12 + Math.random() * 0.18) * volatility : 0;
    const noise = (Math.random() - 0.5) * 0.034 * volatility;
    const tick = trend + regime * 0.03 * volatility + fastPulse + midPulse + momentum + edgeReversal + squeeze + pullback + breakout + wick + noise;

    market.price = market.price * (1 + tick / 100);
    market.move = clamp(market.move + tick * 0.18, -12.5, 12.5);
    market.points = [...market.points.slice(1), clamp(last + tick * (8.8 + volatility * 3.2), 8, 88)];
  });
}

function updatePositionMark() {
  if (!state.position) return;
  const market = markets.find((item) => item.symbol === state.position.symbol);
  if (!market) return;
  state.position.mark = market.price;
}

function renderAll() {
  const selected = markets[state.selectedIndex];

  els.boardScreen.classList.toggle("hidden", state.page !== "board");
  els.workspaceScreen.classList.toggle("hidden", state.page !== "tool");
  els.workbench.classList.toggle("hidden", state.focus);
  els.focusDesk.classList.toggle("hidden", !state.focus);
  els.focusToggle.textContent = state.focus ? "Expand" : "Focus";

  els.boardBalance.textContent = formatMoney(state.balance);
  els.workBalance.textContent = formatMoney(state.balance);

  renderBoardCards();
  renderRail();
  renderWorkspaceHeader(selected);
  renderMarketStats(selected);
  renderTerms(selected);
  renderDepth(selected);
  renderOrderActions();
  renderPositionBadges(selected);

  drawBoardCharts();
  drawChart(els.mainChart, selected, { entry: selectedEntry(selected), large: true });
  drawChart(els.focusChart, selected, { entry: selectedEntry(selected), large: true, focus: true });
}

function renderBoardCards() {
  markets.forEach((market, index) => {
    const card = document.querySelector(`.chart-card[data-index="${index}"]`);
    const price = document.querySelector(`[data-price-index="${index}"]`);
    const move = document.querySelector(`[data-move-index="${index}"]`);

    if (card) {
      card.classList.toggle("selected", index === state.selectedIndex);
      card.classList.toggle("is-hidden", !marketMatchesSearch(market));
    }
    if (price) price.textContent = formatPrice(market.price);
    if (move) {
      move.textContent = formatPercent(market.move);
      move.className = `card-move ${market.move >= 0 ? "move-up" : "move-down"}`;
    }
  });
}

function marketMatchesSearch(market) {
  if (!state.search) return true;
  return `${market.symbol} ${market.name} ${market.assetClass}`.toLowerCase().includes(state.search);
}

function renderRail() {
  els.marketRail.innerHTML = markets
    .map(
      (market, index) => `
        <button class="rail-button ${index === state.selectedIndex ? "active" : ""}" data-rail-index="${index}">
          <div>
            <div class="rail-symbol">${market.symbol}</div>
            <div class="rail-name">${market.name}</div>
          </div>
          <div class="${market.move >= 0 ? "move-up" : "move-down"}">${formatPercent(market.move)}</div>
        </button>
      `
    )
    .join("");

  els.marketRail.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedIndex = Number(button.dataset.railIndex);
      renderAll();
    });
  });
}

function renderWorkspaceHeader(market) {
  setText("workSymbol", market.symbol);
  setText("workName", market.name);
  setText("workPrice", formatPrice(market.price));
  setMove("workMove", market.move);
  setText("deskAssetClass", market.assetClass);
  setText("deskTitle", `${market.symbol} ${market.name}`);
  setText("deskPrice", formatPrice(market.price));
  setMove("deskMove", market.move);
  setText("orderTitle", `${market.symbol} trade`);
  setText("focusSymbol", market.symbol);
  setText("focusPrice", formatPrice(market.price));
}

function renderMarketStats(market) {
  const stats = getMarketStats(market);
  els.marketStats.innerHTML = `
    <div><span>Mark</span><strong>${formatPrice(market.price)}</strong></div>
    <div><span>Index</span><strong>${formatPrice(stats.indexPrice)}</strong></div>
    <div><span>Funding</span><strong class="${stats.funding >= 0 ? "move-up" : "move-down"}">${formatFunding(stats.funding)}</strong></div>
    <div><span>Spread</span><strong>${stats.spreadBps.toFixed(1)} bps</strong></div>
    <div><span>Open interest</span><strong>${formatCompactMoney(stats.openInterest)}</strong></div>
    <div><span>24h volume</span><strong>${formatCompactMoney(stats.volume24h)}</strong></div>
  `;
}

function renderTerms(market) {
  const leverage = Math.min(state.leverage, market.maxLeverage);
  const notional = state.stake * leverage;
  const openFee = notional * 0.0004;
  const liqMove = (100 / leverage) * 0.78;

  setText("termSize", formatMoney(state.stake));
  setText("termLeverage", `${leverage}x`);
  setText("termNotional", formatMoney(notional));
  setText("termFee", formatMoney(openFee));
  setText("termLiq", `${liqMove.toFixed(2)}%`);
  setText("termRoute", market.venue);

  els.stakePresets.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.stake) === state.stake);
  });
  els.leveragePresets.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.leverage) === state.leverage);
  });
}

function renderDepth(market) {
  const rows = getDepthRows(market);
  els.depthRows.innerHTML = rows
    .map(
      (row) => `
        <div class="depth-row ${row.side}">
          <span>${formatPrice(row.price)}</span>
          <strong>${row.size.toFixed(row.size >= 10 ? 0 : 2)}</strong>
        </div>
      `
    )
    .join("");
}

function renderOrderActions() {
  if (state.position) {
    const pnl = getLivePnl();
    els.orderActions.innerHTML = `
      <button id="closeButton" class="trade-button close">Close ${pnl ? formatSignedMoney(pnl.usd) : ""}</button>
    `;
    document.getElementById("closeButton").addEventListener("click", closePosition);
  } else {
    els.orderActions.innerHTML = `
      <button id="longButton" class="trade-button long">Up</button>
      <button id="shortButton" class="trade-button short">Down</button>
    `;
    document.getElementById("longButton").addEventListener("click", () => openPosition("up"));
    document.getElementById("shortButton").addEventListener("click", () => openPosition("down"));
  }

  document.getElementById("focusLong").classList.toggle("hidden", Boolean(state.position));
  document.getElementById("focusShort").classList.toggle("hidden", Boolean(state.position));
  document.getElementById("focusClose").classList.toggle("hidden", !state.position);
}

function renderPositionBadges(market) {
  const pnl = getLivePnl();
  const isSelectedPosition = state.position && state.position.symbol === market.symbol && pnl;

  if (isSelectedPosition) {
    const direction = state.position.direction === "up" ? "UP" : "DOWN";
    els.positionBadge.classList.remove("hidden");
    els.positionBadge.innerHTML = `
      <span>${market.symbol} ${direction} ${state.position.leverage}x</span>
      <strong class="${pnl.usd >= 0 ? "move-up" : "move-down"}">${formatSignedMoney(pnl.usd)}</strong>
      <span>${formatPercent(pnl.pct)}</span>
    `;
    document.getElementById("focusPnl").classList.remove("hidden");
    document.getElementById("focusPnl").className = `focus-pnl ${pnl.usd >= 0 ? "move-up" : "move-down"}`;
    document.getElementById("focusPnl").textContent = formatSignedMoney(pnl.usd);
    document.getElementById("focusClose").textContent = `Close ${formatSignedMoney(pnl.usd)}`;
  } else {
    els.positionBadge.classList.add("hidden");
    document.getElementById("focusPnl").classList.add("hidden");
    document.getElementById("focusPnl").textContent = "";
    document.getElementById("focusClose").textContent = "Close";
  }
}

function drawBoardCharts() {
  document.querySelectorAll(".card-canvas").forEach((canvas) => {
    const index = Number(canvas.dataset.chartIndex);
    drawChart(canvas, markets[index], { mini: true });
  });
}

function openPosition(direction) {
  if (state.position) return;
  const market = markets[state.selectedIndex];
  const leverage = Math.min(state.leverage, market.maxLeverage);
  const fee = state.stake * leverage * 0.0004;

  if (state.balance < state.stake + fee) return;

  state.balance = round(state.balance - state.stake - fee);
  state.position = {
    symbol: market.symbol,
    direction,
    entry: market.price,
    entryPoint: market.points[market.points.length - 1] ?? 50,
    mark: market.price,
    stake: state.stake,
    leverage,
    openedAt: Date.now()
  };

  renderAll();
}

function closePosition() {
  const pnl = getLivePnl();
  if (!state.position || !pnl) return;

  const fee = Math.max(0, pnl.usd) * 0.2;
  const returned = Math.max(0, state.position.stake + pnl.usd - fee);
  state.balance = round(state.balance + returned);
  state.position = null;
  renderAll();
}

function getLivePnl() {
  if (!state.position) return null;
  const side = state.position.direction === "up" ? 1 : -1;
  const move = ((state.position.mark - state.position.entry) / state.position.entry) * side;
  const usd = state.position.stake * state.position.leverage * move;

  return {
    usd,
    pct: (usd / state.position.stake) * 100
  };
}

function selectedEntry(market) {
  if (!state.position || state.position.symbol !== market.symbol) return null;

  return {
    value: state.position.entryPoint,
    direction: state.position.direction
  };
}

function getMarketStats(market) {
  const seed = market.symbol.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const funding = clamp(market.move * 0.003 + ((seed % 11) - 5) * 0.001, -0.048, 0.048);
  const spreadBps = 0.6 + (seed % 8) * 0.18 + market.volatility * 0.22;

  return {
    indexPrice: market.price * (1 + (((seed % 9) - 4) * 0.00012)),
    funding,
    spreadBps,
    openInterest: 90_000_000 + (seed % 17) * 74_000_000 + Math.abs(market.move) * 48_000_000,
    volume24h: 180_000_000 + (seed % 23) * 96_000_000 + market.volatility * 720_000_000
  };
}

function getDepthRows(market) {
  const stats = getMarketStats(market);
  const step = market.price * (stats.spreadBps / 10000);
  const seed = market.symbol.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const rows = [];

  for (let level = 3; level >= 1; level -= 1) {
    rows.push({
      side: "ask",
      price: market.price + step * level,
      size: 2.2 + ((seed + level * 7) % 19) * 0.78
    });
  }

  for (let level = 1; level <= 3; level += 1) {
    rows.push({
      side: "bid",
      price: market.price - step * level,
      size: 2.4 + ((seed + level * 11) % 21) * 0.72
    });
  }

  return rows;
}

function drawChart(canvas, market, options = {}) {
  if (!canvas || !market) return;

  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);
  const dpr = window.devicePixelRatio || 1;

  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const mini = Boolean(options.mini);
  const focus = Boolean(options.focus);
  const pro = !mini && !focus;
  const left = mini ? 14 : 58;
  const right = mini ? width - 14 : width - 92;
  const top = mini ? 30 : pro ? 24 : 44;
  const bottom = mini ? height - 36 : height - 54;
  const points = market.points.slice(mini ? -110 : pro ? -160 : -210);
  const candles = pro ? buildCandles(points, 5) : [];
  const rangeValues = pro ? candles.flatMap((candle) => [candle.high, candle.low, candle.open, candle.close]) : points;
  const values = options.entry ? [...rangeValues, options.entry.value] : rangeValues;
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const rawSpan = Math.max(1, rawMax - rawMin);
  const bottomPad = rawSpan * (pro ? 0.18 : 0.22) + 2;
  const topPad = rawSpan * (pro ? 0.16 : 0.22) + 2;
  const min = rawMin - bottomPad;
  const max = rawMax + topPad;
  const span = Math.max(1, max - min);
  const lastPoint = points[points.length - 1] ?? 50;
  const toX = (index) => left + (index / Math.max(1, points.length - 1)) * (right - left);
  const toY = (value) => bottom - ((value - min) / span) * (bottom - top);
  const coords = points.map((point, index) => ({ x: toX(index), y: toY(point), value: point }));
  const last = coords[coords.length - 1] ?? { x: right, y: bottom, value: lastPoint };
  const candleCoords = candles.map((candle, index) => {
    const x = left + ((index + 0.5) / Math.max(1, candles.length)) * (right - left);
    return {
      ...candle,
      x,
      openY: toY(candle.open),
      closeY: toY(candle.close),
      highY: toY(candle.high),
      lowY: toY(candle.low)
    };
  });
  const up = market.move >= 0;

  const bg = ctx.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, market.themeTop);
  bg.addColorStop(1, market.themeBottom);
  ctx.fillStyle = mini ? "rgba(8, 14, 15, 0.18)" : bg;
  ctx.fillRect(0, 0, width, height);

  drawGrid(ctx, width, height, left, right, top, bottom, mini);
  drawVolume(ctx, coords, bottom, mini);

  if (pro) {
    drawCandles(ctx, candleCoords, right - left);
  } else {
    const area = ctx.createLinearGradient(0, top, 0, bottom);
    area.addColorStop(0, hexToRgba(market.glow, mini ? 0.24 : 0.3));
    area.addColorStop(0.68, hexToRgba(market.accent, mini ? 0.1 : 0.16));
    area.addColorStop(1, hexToRgba(market.accent, 0));
    ctx.beginPath();
    traceSmoothPath(ctx, coords);
    ctx.lineTo(last.x, bottom);
    ctx.lineTo(coords[0].x, bottom);
    ctx.closePath();
    ctx.fillStyle = area;
    ctx.fill();
  }

  if (options.entry) {
    const entryY = clamp(toY(options.entry.value), top + 6, bottom - 6);
    ctx.save();
    ctx.setLineDash([7, 7]);
    ctx.strokeStyle = "rgba(236, 222, 183, 0.48)";
    ctx.lineWidth = mini ? 0.8 : 1.2;
    ctx.beginPath();
    ctx.moveTo(left, entryY);
    ctx.lineTo(right, entryY);
    ctx.stroke();
    ctx.restore();
  }

  if (!pro) drawLine(ctx, coords, market, mini);

  if (!mini) {
    drawCurrentPriceLine(ctx, left, right, last.y, up);
    drawAxisLabels(ctx, market.price, lastPoint, min, span, top, bottom, right);
    drawTimeLabels(ctx, left, right, bottom);
    drawPriceTag(ctx, right, last.y, market.price, up);
  }

  if (!pro) {
    ctx.beginPath();
    ctx.arc(last.x, last.y, mini ? 3.2 : 5.5, 0, Math.PI * 2);
    ctx.fillStyle = up ? "#38c884" : "#ed5b67";
    ctx.fill();
  }
}

function buildCandles(points, groupSize) {
  const candles = [];

  for (let index = 0; index < points.length - groupSize; index += groupSize) {
    const group = points.slice(index, index + groupSize);
    const open = group[0];
    const close = group[group.length - 1];
    const high = Math.max(...group);
    const low = Math.min(...group);

    candles.push({ open, close, high, low });
  }

  return candles;
}

function drawGrid(ctx, width, height, left, right, top, bottom, mini) {
  ctx.save();
  ctx.strokeStyle = mini ? "rgba(255,255,255,0.035)" : "rgba(255,255,255,0.06)";
  ctx.lineWidth = 1;

  const hLines = mini ? 3 : 5;
  for (let index = 0; index < hLines; index += 1) {
    const y = top + ((bottom - top) / Math.max(1, hLines - 1)) * index;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
  }

  const vLines = mini ? 3 : 6;
  for (let index = 0; index < vLines; index += 1) {
    const x = left + ((right - left) / Math.max(1, vLines - 1)) * index;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
  }

  ctx.restore();
}

function drawVolume(ctx, coords, bottom, mini) {
  const step = mini ? 5 : 4;
  ctx.save();

  for (let index = 1; index < coords.length; index += step) {
    const current = coords[index];
    const previous = coords[index - 1] ?? current;
    const delta = current.value - previous.value;
    const magnitude = clamp(Math.abs(delta) / 2.4, 0.08, 1);
    const barHeight = (mini ? 12 : 26) * magnitude + 2;
    ctx.fillStyle = delta >= 0 ? `rgba(56,200,132,${mini ? 0.12 : 0.16})` : `rgba(237,91,103,${mini ? 0.12 : 0.16})`;
    ctx.fillRect(current.x - (mini ? 1 : 1.2), bottom - barHeight, mini ? 2 : 2.4, barHeight);
  }

  ctx.restore();
}

function drawCandles(ctx, candles, chartWidth) {
  const candleWidth = clamp((chartWidth / Math.max(1, candles.length)) * 0.56, 4, 13);

  ctx.save();

  candles.forEach((candle) => {
    const isUp = candle.close >= candle.open;
    const bodyTop = Math.min(candle.openY, candle.closeY);
    const bodyHeight = Math.max(3, Math.abs(candle.closeY - candle.openY));

    ctx.strokeStyle = isUp ? "rgba(56,200,132,0.72)" : "rgba(237,91,103,0.72)";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(candle.x, candle.highY);
    ctx.lineTo(candle.x, candle.lowY);
    ctx.stroke();

    ctx.fillStyle = isUp ? "rgba(56,200,132,0.34)" : "rgba(237,91,103,0.34)";
    roundedRect(ctx, candle.x - candleWidth / 2, bodyTop, candleWidth, bodyHeight, 2);
    ctx.fill();
    ctx.stroke();
  });

  ctx.restore();
}

function drawLine(ctx, coords, market, mini) {
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  ctx.strokeStyle = hexToRgba(market.accent, mini ? 0.1 : 0.09);
  ctx.lineWidth = mini ? 10 : 18;
  ctx.beginPath();
  traceSmoothPath(ctx, coords);
  ctx.stroke();

  ctx.strokeStyle = hexToRgba(market.accent, mini ? 0.3 : 0.24);
  ctx.lineWidth = mini ? 5 : 8;
  ctx.beginPath();
  traceSmoothPath(ctx, coords);
  ctx.stroke();

  ctx.strokeStyle = market.accent;
  ctx.lineWidth = mini ? 2.1 : 3;
  ctx.beginPath();
  traceSmoothPath(ctx, coords);
  ctx.stroke();

  ctx.strokeStyle = hexToRgba(market.glow, mini ? 0.3 : 0.38);
  ctx.lineWidth = mini ? 1.2 : 1.8;
  ctx.beginPath();
  traceSmoothPath(ctx, coords.slice(Math.max(0, coords.length - 30)));
  ctx.stroke();

  ctx.restore();
}

function drawCurrentPriceLine(ctx, left, right, y, up) {
  ctx.save();
  ctx.setLineDash([5, 7]);
  ctx.strokeStyle = up ? "rgba(56,200,132,0.34)" : "rgba(237,91,103,0.34)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left, y);
  ctx.lineTo(right, y);
  ctx.stroke();
  ctx.restore();
}

function drawTimeLabels(ctx, left, right, bottom) {
  ctx.save();
  ctx.fillStyle = "rgba(218,230,226,0.42)";
  ctx.font = "800 11px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";

  ["-30m", "-20m", "-10m", "now"].forEach((label, index) => {
    const x = left + ((right - left) / 3) * index;
    ctx.fillText(label, x, bottom + 28);
  });

  ctx.restore();
}

function traceSmoothPath(ctx, coords) {
  if (!coords.length) return;

  ctx.moveTo(coords[0].x, coords[0].y);

  for (let index = 1; index < coords.length - 1; index += 1) {
    const current = coords[index];
    const next = coords[index + 1];
    const midX = (current.x + next.x) / 2;
    const midY = (current.y + next.y) / 2;
    ctx.quadraticCurveTo(current.x, current.y, midX, midY);
  }

  const last = coords[coords.length - 1];
  ctx.lineTo(last.x, last.y);
}

function drawAxisLabels(ctx, price, lastPoint, min, span, top, bottom, right) {
  ctx.save();
  ctx.fillStyle = "rgba(218,230,226,0.56)";
  ctx.font = "800 12px Inter, system-ui, sans-serif";

  [0.82, 0.62, 0.42, 0.22].forEach((ratio) => {
    const value = min + span * ratio;
    const y = bottom - ((value - min) / span) * (bottom - top);
    const estimatedPrice = price * (1 + (value - lastPoint) * 0.00125);
    ctx.fillText(formatAxisPrice(estimatedPrice), right + 16, y + 4);
  });

  ctx.restore();
}

function drawPriceTag(ctx, right, y, price, up) {
  const tagY = clamp(y - 13, 18, ctx.canvas.height - 40);
  ctx.save();
  ctx.fillStyle = up ? "#38c884" : "#ed5b67";
  roundedRect(ctx, right + 12, tagY, 72, 26, 13);
  ctx.fill();
  ctx.fillStyle = "#06100d";
  ctx.font = "950 12px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(formatAxisPrice(price), right + 48, tagY + 17);
  ctx.restore();
}

function roundedRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + width, y, x + width, y + height, radius);
  ctx.arcTo(x + width, y + height, x, y + height, radius);
  ctx.arcTo(x, y + height, x, y, radius);
  ctx.arcTo(x, y, x + width, y, radius);
  ctx.closePath();
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setMove(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = formatPercent(value);
  el.className = value >= 0 ? "move-up" : "move-down";
}

function formatPrice(price) {
  if (!Number.isFinite(price)) return "$0.00";
  if (price < 1) return `$${price.toFixed(4)}`;
  if (price < 10) return `$${price.toFixed(4)}`;
  if (price < 100) return `$${price.toFixed(2)}`;
  return `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatMoney(value) {
  const safeValue = Number.isFinite(value) ? value : 0;
  return `$${safeValue.toFixed(2)}`;
}

function formatCompactMoney(value) {
  const safeValue = Math.abs(Number.isFinite(value) ? value : 0);
  if (safeValue >= 1_000_000_000) return `$${(safeValue / 1_000_000_000).toFixed(2)}B`;
  if (safeValue >= 1_000_000) return `$${(safeValue / 1_000_000).toFixed(1)}M`;
  if (safeValue >= 1_000) return `$${(safeValue / 1_000).toFixed(1)}K`;
  return `$${safeValue.toFixed(0)}`;
}

function formatSignedMoney(value) {
  const safeValue = Number.isFinite(value) ? value : 0;
  return `${safeValue >= 0 ? "+" : "-"}$${Math.abs(safeValue).toFixed(2)}`;
}

function formatPercent(value) {
  const safeValue = Number.isFinite(value) ? value : 0;
  return `${safeValue >= 0 ? "+" : ""}${safeValue.toFixed(1)}%`;
}

function formatFunding(value) {
  const safeValue = Number.isFinite(value) ? value : 0;
  return `${safeValue >= 0 ? "+" : ""}${safeValue.toFixed(3)}%`;
}

function formatAxisPrice(price) {
  if (!Number.isFinite(price)) return "0";
  if (price < 1) return price.toFixed(4);
  if (price < 10) return price.toFixed(4);
  if (price < 100) return price.toFixed(2);
  if (price < 1000) return price.toFixed(1);
  return Math.round(price).toLocaleString(undefined, { useGrouping: false });
}

function hexToRgba(hex, alpha) {
  const value = hex.replace("#", "");
  const bigint = parseInt(value, 16);
  const r = (bigint >> 16) & 255;
  const g = (bigint >> 8) & 255;
  const b = bigint & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

function round(value) {
  return Math.round(value * 100) / 100;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
