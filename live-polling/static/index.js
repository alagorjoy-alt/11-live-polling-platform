(() => {
  const MIN_OPTIONS = 2, MAX_OPTIONS = 10;
  const optionsEl = document.getElementById("options");
  const addBtn = document.getElementById("add-option");
  const form = document.getElementById("create-form");
  const msg = document.getElementById("create-msg");
  const createBtn = document.getElementById("create-btn");

  function errorText(data, fallback) {
    if (!data) return fallback;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map(d => (d.msg || "").replace(/^Value error, /, "")).join(". ");
    }
    return fallback;
  }

  function optionInputs() { return [...optionsEl.querySelectorAll("input")]; }

  function addOption(value = "") {
    if (optionInputs().length >= MAX_OPTIONS) return;
    const row = document.createElement("div");
    row.className = "option-row";
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 100;
    input.value = value;
    input.setAttribute("aria-label", "Option " + (optionInputs().length + 1));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      if (optionInputs().length > MIN_OPTIONS) { row.remove(); refresh(); }
    });
    row.append(input, remove);
    optionsEl.appendChild(row);
    refresh();
  }

  function refresh() {
    const n = optionInputs().length;
    addBtn.disabled = n >= MAX_OPTIONS;
    optionsEl.querySelectorAll("button").forEach(b => (b.disabled = n <= MIN_OPTIONS));
    optionInputs().forEach((el, i) => el.setAttribute("aria-label", "Option " + (i + 1)));
  }

  addBtn.addEventListener("click", () => { addOption(); optionInputs().at(-1).focus(); });
  addOption(); addOption();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msg.className = "msg"; msg.textContent = "";
    const question = document.getElementById("question").value.trim();
    const options = optionInputs().map(i => i.value.trim());
    const duration = document.getElementById("duration").value;

    // Quick client-side checks; the server validates again.
    if (question.length < 3) return fail("Enter a question of at least 3 characters.");
    if (options.some(o => !o)) return fail("Fill in every option or remove the empty ones.");
    if (new Set(options.map(o => o.toLowerCase())).size !== options.length) return fail("Options must be different from each other.");

    createBtn.disabled = true;
    try {
      const res = await fetch("/api/polls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, options, duration_minutes: duration ? Number(duration) : null }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(errorText(data, "Could not create the poll."));
      try { localStorage.setItem("admin:" + data.id, data.admin_token); } catch (_) {}
      location.href = "/p/" + data.id;
    } catch (err) {
      fail(err.message || "Network error. Try again.");
      createBtn.disabled = false;
    }
  });

  function fail(text) { msg.className = "msg error"; msg.textContent = text; }

  async function loadRecent() {
    const list = document.getElementById("poll-list");
    const empty = document.getElementById("empty");
    try {
      const res = await fetch("/api/polls");
      const polls = await res.json();
      list.replaceChildren();
      empty.hidden = polls.length > 0;
      for (const p of polls) {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = "/p/" + p.id;
        const q = document.createElement("div");
        q.className = "q"; q.textContent = p.question;
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = `${p.total_votes} ${p.total_votes === 1 ? "vote" : "votes"}, ${p.is_closed ? "closed" : "open"}`;
        a.append(q, meta); li.appendChild(a); list.appendChild(li);
      }
    } catch (_) {
      empty.hidden = false; empty.textContent = "Could not load polls. Refresh to try again.";
    }
  }
  loadRecent();
})();
