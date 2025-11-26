const API_BASE = window.API_BASE || "/api/minesweeper";
const IMG_BASE = "/assets/tiles";
const _params = new URLSearchParams(window.location.search);
const EXTERNAL_USER_ID = _params.get("x-user-id");
const EXTERNAL_USER_NAME = _params.get("x-user-name");
let USER_ID = EXTERNAL_USER_ID || localStorage.getItem("ms_user");
if (!USER_ID) {
  const rnd = Math.random().toString(36).slice(2);
  const ts = Date.now().toString(36);
  USER_ID = `u_${ts}_${rnd}`;
}
localStorage.setItem("ms_user", USER_ID);

const el = (id) => document.getElementById(id);
const boardEl = el("board");
const statusText = el("status-text");
const minesLeftEl = el("mines-left");
const movesCountEl = el("moves-count");
const overlay = el("overlay");
const overlayError = el("overlay-error");
const widthInput = el("width-input");
const heightInput = el("height-input");
const minesInput = el("mines-input");
const startBtn = el("start-game");
const abortBtn = el("abort-game");
const resultBanner = el("result-banner");
const continueBtn = el("continue-game");
const loadingEl = el("loading");
const trackedIndicator = el("tracked-indicator");
const toastEl = el("toast");
const toastMessage = el("toast-message");
const presetBtns = document.querySelectorAll(".preset-btn");
const MAX_DIM = 40;

let toastTimeout = null;
function showToast(message, duration = 4000) {
  if (!toastEl || !toastMessage) return;
  toastMessage.textContent = message;
  toastEl.classList.remove("hidden");
  if (toastTimeout) clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toastEl.classList.add("hidden");
  }, duration);
}

// Tracked game modes for leaderboards
const TRACKED_MODES = [
  { width: 8, height: 8, mines: 10, name: "Beginner" },
  { width: 16, height: 16, mines: 40, name: "Intermediate" },
  { width: 30, height: 16, mines: 99, name: "Hard" },
  { width: 30, height: 22, mines: 200, name: "Extreme" },
];

let pendingRequests = 0;
let revealedTiles = new Set(); // Track tiles revealed during gameplay

function setLoadingVisible(show) {
  if (!loadingEl) return;
  if (show) {
    loadingEl.classList.remove("hidden");
  } else {
    loadingEl.classList.add("hidden");
  }
}

function beginRequest() {
  pendingRequests++;
  setLoadingVisible(true);
}

function endRequest() {
  pendingRequests = Math.max(0, pendingRequests - 1);
  if (pendingRequests === 0) setLoadingVisible(false);
}

function isTrackedMode(w, h, m) {
  return TRACKED_MODES.some(
    (mode) => mode.width === w && mode.height === h && mode.mines === m
  );
}

function updateTrackedIndicator() {
  const w = parseInt(widthInput.value, 10) || 0;
  const h = parseInt(heightInput.value, 10) || 0;
  const m = parseInt(minesInput.value, 10) || 0;
  if (trackedIndicator) {
    if (isTrackedMode(w, h, m)) {
      trackedIndicator.classList.remove("hidden");
    } else {
      trackedIndicator.classList.add("hidden");
    }
  }
  // Update preset button active states
  presetBtns.forEach((btn) => {
    const bw = parseInt(btn.dataset.width, 10);
    const bh = parseInt(btn.dataset.height, 10);
    const bm = parseInt(btn.dataset.mines, 10);
    if (bw === w && bh === h && bm === m) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

function validateDims() {
  const w = parseInt(widthInput.value, 10) || 0;
  const h = parseInt(heightInput.value, 10) || 0;
  if (w > MAX_DIM || h > MAX_DIM) {
    overlayError.textContent = `Max board size is ${MAX_DIM}×${MAX_DIM}. Reduce width/height.`;
    if (startBtn) startBtn.disabled = true;
  } else {
    overlayError.textContent = "";
    if (startBtn) startBtn.disabled = false;
  }
  updateTrackedIndicator();
}

async function api(path, method = "GET", body, showLoading = false) {
  if (showLoading) beginRequest();
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-User-Id": USER_ID,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`${res.status}: ${txt}`);
    }
    return res.json();
  } finally {
    if (showLoading) endRequest();
  }
}

function render(data) {
  const { board, status, num_mines, flags_total, board_width, board_height, moves_count } = data;
  statusText.textContent = status;
  movesCountEl.textContent = moves_count ?? 0;
  const minesLeft = (num_mines ?? 0) - (flags_total ?? 0);
  minesLeftEl.textContent = minesLeft;

  const last = data.last_move || null;
  const isLost = status === "lost";

  // If game is active, update the set of revealed tiles
  if (status === "active") {
    for (let r = 0; r < board_height; r++) {
      for (let c = 0; c < board_width; c++) {
        const v = board[r][c];
        // A tile is revealed if it's a number (0-8)
        if (v !== "H" && v !== "F" && v !== "M") {
          revealedTiles.add(`${r},${c}`);
        }
      }
    }
  }

  boardEl.style.gridTemplateColumns = `repeat(${board_width}, 28px)`;
  boardEl.innerHTML = "";
  for (let r = 0; r < board_height; r++) {
    for (let c = 0; c < board_width; c++) {
      const v = board[r][c];
      const t = document.createElement("div");
      t.className = "tile";
      t.dataset.r = r;
      t.dataset.c = c;

      let img = null;
      if (v === "H") {
        img = "unrevealed.png";
      } else if (v === "F") {
        img = "flag.png";
        t.classList.add("flag");
      } else if (v === "M") {
        if (last && last.hit_mine && last.row === r && last.col === c) {
          img = "boom.png";
        } else {
          img = "bomb.png";
        }
        t.classList.add("mine");
      } else {
        img = `${v}.png`;
        t.classList.add("revealed");
        // On loss, dim tiles that were auto-revealed (not revealed by the player)
        if (isLost && !revealedTiles.has(`${r},${c}`)) {
          t.classList.add("auto-revealed");
        }
      }

      t.textContent = "";
      t.style.backgroundImage = img ? `url('${IMG_BASE}/${img}')` : "";

      if (status === "active") {
        t.addEventListener("click", async () => {
          try {
            const resp = await api("/reveal", "POST", { row: r, col: c });
            render(resp);
          } catch (e) {
            console.error(e);
          }
        });
        t.addEventListener("contextmenu", async (ev) => {
          ev.preventDefault();
          try {
            const resp = await api("/flag", "POST", { row: r, col: c });
            render(resp);
          } catch (e) {
            console.error(e);
          }
        });
      }

      boardEl.appendChild(t);
    }
  }
  if (abortBtn) {
    abortBtn.disabled = status !== "active";
  }
  // Post-game UI for won/lost: keep board visible, show banner and Continue
  const postGame = status === "won" || status === "lost";
  if (resultBanner) {
    if (status === "won") {
      resultBanner.textContent = "Victory";
      resultBanner.classList.remove("hidden");
      resultBanner.classList.add("win");
      resultBanner.classList.remove("lose");
    } else if (status === "lost") {
      resultBanner.textContent = "You lose";
      resultBanner.classList.remove("hidden");
      resultBanner.classList.add("lose");
      resultBanner.classList.remove("win");
    } else {
      resultBanner.textContent = "";
      resultBanner.classList.add("hidden");
      resultBanner.classList.remove("win");
      resultBanner.classList.remove("lose");
    }
  }
  if (continueBtn) {
    continueBtn.classList.toggle("hidden", !postGame);
  }
  // Show toast if leaderboard recording failed
  if (postGame && state.leaderboard_error) {
    showToast("Failed to record leaderboard entry");
  }
  // Only show overlay for abandoned or error; not for normal end states
  setOverlayVisible(status === "abandoned" || status === "error");
}

async function load() {
  try {
    const s = await api("/state", "GET", undefined, true);
    render(s);
  } catch (e) {
    if (String(e).startsWith("Error: 404")) {
      setOverlayVisible(true);
    } else {
      console.error(e);
    }
  }
}

async function startNew() {
  const w = parseInt(widthInput.value, 10) || 10;
  const h = parseInt(heightInput.value, 10) || 10;
  const m = parseInt(minesInput.value, 10) || 10;
  if (w > MAX_DIM || h > MAX_DIM) {
    overlayError.textContent = `Max board size is ${MAX_DIM}×${MAX_DIM}. You entered ${w}×${h}.`;
    return;
  }
  // Reset revealed tiles for new game
  revealedTiles = new Set();
  try {
    const s = await api("/start", "POST", { board_width: w, board_height: h, num_mines: m }, true);
    render(s);
    setOverlayVisible(false);
    overlayError.textContent = "";
  } catch (e) {
    if (String(e).startsWith("Error: 409")) {
      const s = await api("/state", "GET", undefined, true);
      render(s);
      setOverlayVisible(false);
      overlayError.textContent = "";
    } else {
      overlayError.textContent = String(e).replace(/^Error: \d+:\s*/, "");
      console.error(e);
    }
  }
}

function setOverlayVisible(show) {
  if (!overlay) return;
  if (show) {
    overlay.classList.remove("hidden");
    document.body.classList.add("modal-open");
  } else {
    overlay.classList.add("hidden");
    document.body.classList.remove("modal-open");
  }
}

if (startBtn) startBtn.addEventListener("click", startNew);
if (widthInput) widthInput.addEventListener("input", validateDims);
if (heightInput) heightInput.addEventListener("input", validateDims);
if (minesInput) minesInput.addEventListener("input", updateTrackedIndicator);

// Preset mode button handlers
presetBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    const w = btn.dataset.width;
    const h = btn.dataset.height;
    const m = btn.dataset.mines;
    if (widthInput) widthInput.value = w;
    if (heightInput) heightInput.value = h;
    if (minesInput) minesInput.value = m;
    validateDims();
  });
});

validateDims();
if (abortBtn) abortBtn.addEventListener("click", async () => {
  abortBtn.disabled = true;
  try {
    const s = await api("/abandon", "POST");
    render(s);
  } catch (e) {
    console.error(e);
  } finally {
    abortBtn.disabled = false;
  }
});

if (continueBtn) continueBtn.addEventListener("click", () => {
  if (overlayError) overlayError.textContent = "";
  setOverlayVisible(true);
});

load();
