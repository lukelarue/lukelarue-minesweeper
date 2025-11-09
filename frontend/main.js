const API_BASE = window.API_BASE || "/api/minesweeper";
const IMG_BASE = "/assets/tiles";
const USER_ID = localStorage.getItem("ms_user") || "demo";
localStorage.setItem("ms_user", USER_ID);

const el = (id) => document.getElementById(id);
const boardEl = el("board");
const statusText = el("status-text");
const minesLeftEl = el("mines-left");
const movesCountEl = el("moves-count");

async function api(path, method = "GET", body) {
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
}

function render(data) {
  const { board, status, num_mines, flags_total, board_width, board_height, moves_count } = data;
  statusText.textContent = status;
  movesCountEl.textContent = moves_count ?? 0;
  const minesLeft = (num_mines ?? 0) - (flags_total ?? 0);
  minesLeftEl.textContent = minesLeft;

  const last = data.last_move || null;

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
      } else if (v === "M") {
        if (last && last.hit_mine && last.row === r && last.col === c) {
          img = "boom.png";
        } else {
          img = "bomb.png";
        }
      } else {
        // revealed number 0-8
        img = `${v}.png`;
        t.classList.add("revealed");
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
}

async function load() {
  try {
    const s = await api("/state");
    render(s);
  } catch (e) {
    // if no active game, create one
    await startNew();
  }
}

async function startNew() {
  const w = parseInt(el("w").value, 10) || 10;
  const h = parseInt(el("h").value, 10) || 10;
  const m = parseInt(el("m").value, 10) || 10;
  try {
    const s = await api("/start", "POST", { board_width: w, board_height: h, num_mines: m });
    render(s);
  } catch (e) {
    if (String(e).startsWith("Error: 409")) {
      const s = await api("/state");
      render(s);
    } else {
      console.error(e);
    }
  }
}

el("new-game").addEventListener("click", startNew);

load();
