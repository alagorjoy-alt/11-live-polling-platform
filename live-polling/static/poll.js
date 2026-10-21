(() => {
  const pollId = location.pathname.split("/").filter(Boolean).pop();
  const $ = (id) => document.getElementById(id);
  const state = { closed: false, closesAt: null, myVote: null, options: [] };
  let chart = null, ws = null, retries = 0, heartbeat = null;

  function errorText(data, fallback) {
    if (!data) return fallback;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map(d => d.msg).join(". ");
    return fallback;
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const err = new Error(errorText(data, "Something went wrong."));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function setMessage(text, kind) {
    const el = $("msg");
    el.textContent = text || "";
    el.className = "msg" + (kind ? " " + kind : "");
  }

  function setStatus(label, kind) {
    const el = $("status");
    el.textContent = label;
    el.className = "pill " + kind;
  }

  // ---------- chart ----------
  function buildChart() {
    chart = new Chart($("chart"), {
      type: "bar",
      data: { labels: [], datasets: [{ data: [], backgroundColor: "#3a5bff", borderRadius: 6 }] },
      options: {
        indexAxis: "y",
        maintainAspectRatio: false,
        animation: { duration: 350 },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const opt = state.options[ctx.dataIndex];
                return opt ? `${opt.votes} votes (${opt.percent}%)` : "";
              },
            },
          },
        },
        scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  function applyResults(msg) {
    state.options = msg.options;
    $("total").textContent = msg.total_votes;
    if (msg.is_closed && !state.closed) markClosed();
    if (!chart) return;
    chart.data.labels = msg.options.map(o => o.label);
    chart.data.datasets[0].data = msg.options.map(o => o.votes);
    chart.update();
  }

  // ---------- vote form ----------
  function renderChoices(options) {
    const box = $("choices");
    box.querySelectorAll(".choice").forEach(n => n.remove());
    for (const o of options) {
      const label = document.createElement("label");
      label.className = "choice" + (state.myVote === o.id ? " mine" : "");
      const input = document.createElement("input");
      input.type = "radio"; input.name = "option"; input.value = o.id;
      input.checked = state.myVote === o.id;
      const text = document.createElement("span");
      text.textContent = o.label;
      label.append(input, text);
      box.appendChild(label);
    }
    updateFormState();
  }

  function updateFormState() {
    const locked = state.closed || state.myVote !== null;
    document.querySelectorAll("#choices input").forEach(i => (i.disabled = locked));
    $("vote-btn").disabled = locked;
    if (state.myVote !== null) setMessage("You voted. Results update live.", "success");
    else if (state.closed) setMessage("This poll is closed.", "error");
  }

  function markClosed() {
    state.closed = true;
    setStatus("Closed", "closed");
    $("closed-note").textContent = "Voting has ended. Final results are shown.";
    $("close-btn").hidden = true;
    updateFormState();
  }

  $("vote-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const picked = document.querySelector("#choices input:checked");
    if (!picked) return setMessage("Choose an option first.", "error");
    $("vote-btn").disabled = true;
    try {
      const data = await api(`/api/polls/${pollId}/vote`, {
        method: "POST", body: JSON.stringify({ option_id: Number(picked.value) }),
      });
      state.myVote = data.my_vote;
      applyResults(data);
      renderChoices(data.options);
      setMessage("Vote recorded. Thank you!", "success");
    } catch (err) {
      if (err.status === 409) { await loadPoll(); }  // already voted: sync the UI with the server
      else if (err.status === 410) { markClosed(); }
      else { $("vote-btn").disabled = false; }
      if (err.status !== 409) setMessage(err.message, "error");
      else setMessage(err.message + ".", "error");
    }
  });

  // ---------- admin ----------
  function adminToken() {
    try { return localStorage.getItem("admin:" + pollId); } catch (_) { return null; }
  }
  $("close-btn").addEventListener("click", async () => {
    if (!confirm("Close this poll? Nobody will be able to vote after this.")) return;
    try {
      const data = await api(`/api/polls/${pollId}/close`, {
        method: "POST", headers: { "X-Admin-Token": adminToken() },
      });
      applyResults(data);
      markClosed();
    } catch (err) { setMessage(err.message, "error"); }
  });

  $("copy-btn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("share-url").value);
      $("copy-btn").textContent = "Copied";
    } catch (_) {
      $("share-url").select();
      $("copy-btn").textContent = "Press Ctrl+C";
    }
    setTimeout(() => ($("copy-btn").textContent = "Copy link"), 1800);
  });

  // ---------- websocket with reconnect ----------
  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/polls/${pollId}`);
    ws.onopen = () => {
      retries = 0;
      if (!state.closed) setStatus("Live", "live");
      clearInterval(heartbeat);
      heartbeat = setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000);
    };
    ws.onmessage = (ev) => {
      if (ev.data === "pong") return;
      const msg = JSON.parse(ev.data);
      if (msg.type === "results") applyResults(msg);
    };
    ws.onclose = () => {
      clearInterval(heartbeat);
      if (state.closed) return;
      setStatus("Reconnecting", "wait");
      const delay = Math.min(1000 * 2 ** retries++, 10000);
      setTimeout(connect, delay);
    };
  }

  // ---------- load ----------
  async function loadPoll() {
    const poll = await api(`/api/polls/${pollId}`);
    state.closed = poll.is_closed;
    state.closesAt = poll.closes_at;
    state.myVote = poll.my_vote;
    $("question").textContent = poll.question;
    document.title = poll.question + " | Show of Hands";
    renderChoices(poll.options);
    applyResults(poll);
    if (poll.is_closed) markClosed();
    return poll;
  }

  async function init() {
    $("share-url").value = location.href;
    try {
      if (window.Chart) buildChart();  // page still works (numbers only) if the CDN is blocked
      await loadPoll();
    } catch (err) {
      $("error-panel").hidden = false;
      return;
    }
    $("poll-view").hidden = false;
    if (adminToken() && !state.closed) $("close-btn").hidden = false;
    if (!state.closed) connect(); else setStatus("Closed", "closed");

    // Polls with a time limit close themselves; reflect that without a page reload.
    if (state.closesAt) {
      const timer = setInterval(() => {
        if (Date.now() >= Date.parse(state.closesAt)) { clearInterval(timer); markClosed(); }
      }, 1000);
    }
  }
  init();
})();
