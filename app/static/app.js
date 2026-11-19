"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const CATEGORY_LABELS = {
    routine: "Daily routine",
    indoor: "Indoor air",
    alternative: "Greener alternatives",
  };
  const PRIORITY_LABELS = { 1: "Do first", 2: "Next", 3: "Bonus" };

  let place = null; // { name, lat, lon }
  let busy = false;

  function setStatus(message, isError = false) {
    const el = $("status");
    el.textContent = message;
    el.classList.toggle("error", isError);
  }

  async function api(path, options) {
    let response;
    try {
      response = await fetch(path, options);
    } catch {
      throw new Error("Could not reach the server. Check your connection.");
    }
    let data = null;
    try { data = await response.json(); } catch { /* non-JSON body */ }
    if (!response.ok) {
      throw new Error((data && data.error && data.error.message) || "Something went wrong.");
    }
    return data;
  }

  function chosePlace(p) {
    place = p;
    $("chosen").textContent = `Selected: ${p.name}${p.region ? ", " + p.region : ""}`;
    $("results").hidden = true;
    $("results").replaceChildren();
    $("city").value = p.name;
  }

  async function searchPlaces() {
    const q = $("city").value.trim();
    if (q.length < 2) { setStatus("Type at least 2 letters of a city name.", true); $("city").focus(); return; }
    setStatus("Searching places...");
    try {
      const data = await api(`/api/geocode?q=${encodeURIComponent(q)}`);
      const list = $("results");
      list.replaceChildren();
      if (!data.places.length) { setStatus("No places found. Try a nearby city.", true); list.hidden = true; return; }
      for (const p of data.places) {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        const btn = document.createElement("button");
        btn.type = "button";
        const name = document.createElement("strong");
        name.textContent = p.name;
        const region = document.createElement("span");
        region.className = "region";
        region.textContent = p.region ? ` - ${p.region}` : "";
        btn.append(name, region);
        btn.addEventListener("click", () => { chosePlace(p); setStatus(""); $("submit-btn").focus(); });
        li.append(btn);
        list.append(li);
      }
      list.hidden = false;
      setStatus(`${data.places.length} place${data.places.length > 1 ? "s" : ""} found. Choose one.`);
      list.querySelector("button").focus();
    } catch (err) {
      setStatus(err.message, true);
    }
  }

  function useLocation() {
    if (!navigator.geolocation) { setStatus("Your browser does not support location. Search for a city instead.", true); return; }
    setStatus("Finding your location...");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        chosePlace({
          name: "Your location",
          region: "",
          lat: Math.round(pos.coords.latitude * 1000) / 1000,
          lon: Math.round(pos.coords.longitude * 1000) / 1000,
        });
        setStatus("Location found.");
      },
      () => setStatus("Location was blocked. Search for a city instead.", true),
      { timeout: 10000, maximumAge: 300000 },
    );
  }

  function profile() {
    const km = Number($("km").value);
    return {
      commute_mode: $("mode").value,
      commute_km: Number.isFinite(km) ? Math.min(150, Math.max(0, km)) : 0,
      has_children: $("children").checked,
      has_elderly: $("elderly").checked,
      has_respiratory_condition: $("resp").checked,
      has_purifier: $("purifier").checked,
      cooking_fuel: $("fuel").value,
      exercises_outdoors: $("exercise").checked,
    };
  }

  function body(extra = {}) {
    return JSON.stringify({
      location: { lat: place.lat, lon: place.lon, name: place.name },
      profile: profile(),
      ...extra,
    });
  }

  function renderAqi(d) {
    $("aqi-card").dataset.level = String(d.aqi.level);
    $("aqi-number").textContent = String(d.aqi.index);
    $("aqi-cat").textContent = d.aqi.category;
    $("headline").textContent = d.headline;
    $("place").textContent = `${d.place}. Updated ${d.aqi.observed_at.replace("T", " ")} local time.`;
    const dl = $("pollutants");
    dl.replaceChildren();
    const rows = [
      ["PM2.5", d.aqi.pm25], ["PM10", d.aqi.pm10], ["NO2", d.aqi.no2], ["O3", d.aqi.o3],
    ];
    for (const [label, value] of rows) {
      if (value == null) continue;
      const div = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = `${Math.round(value)} µg/m³`;
      div.append(dt, dd);
      dl.append(div);
    }
  }

  function renderWindow(w) {
    const card = $("window-card");
    if (!w) { card.hidden = true; return; }
    card.hidden = false;
    $("window-text").textContent =
      `Cleanest air is expected around ${w.best_time} (AQI ${w.best_aqi}). ` +
      `Worst is around ${w.worst_time} (AQI ${w.worst_aqi}). Plan walks, errands and airing the house accordingly.`;
  }

  function renderImpact(impact, actions) {
    const list = $("impact-list");
    list.replaceChildren();
    const items = [];
    if (impact.weekly_commute_co2_kg > 0) {
      items.push([`${impact.weekly_commute_co2_kg} kg`, "CO₂e from your commute each week"]);
    }
    if (impact.best_option_saving_kg > 0) {
      items.push([
        `${impact.best_option_saving_kg} kg`,
        `CO₂e saved weekly by your biggest swap (${impact.best_option_saving_pct}% of your commute)`,
      ]);
    }
    const first = actions.filter((a) => a.priority === 1).length;
    items.push([String(first), first === 1 ? "high-priority action for today" : "high-priority actions for today"]);
    for (const [big, small] of items) {
      const li = document.createElement("li");
      const b = document.createElement("span");
      b.className = "big";
      b.textContent = big;
      li.append(b, document.createTextNode(small));
      list.append(li);
    }
  }

  function renderPlan(actions) {
    const tabs = $("tabs");
    const panels = $("panels");
    tabs.replaceChildren();
    panels.replaceChildren();
    const cats = Object.keys(CATEGORY_LABELS).filter((c) => actions.some((a) => a.category === c));

    cats.forEach((cat, i) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "tab";
      tab.id = `tab-${cat}`;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-controls", `panel-${cat}`);
      tab.textContent = CATEGORY_LABELS[cat];
      tabs.append(tab);

      const panel = document.createElement("div");
      panel.id = `panel-${cat}`;
      panel.setAttribute("role", "tabpanel");
      panel.setAttribute("aria-labelledby", tab.id);
      const ul = document.createElement("ul");
      ul.className = "actions";
      for (const a of actions.filter((x) => x.category === cat)) {
        const li = document.createElement("li");
        li.className = "action";
        const h = document.createElement("h4");
        const pr = document.createElement("span");
        pr.className = `prio p${a.priority}`;
        pr.textContent = PRIORITY_LABELS[a.priority] || "Next";
        h.append(pr, document.createTextNode(a.title));
        const why = document.createElement("p");
        why.className = "why";
        why.textContent = a.why;
        const imp = document.createElement("p");
        imp.className = "impact";
        imp.textContent = a.impact;
        li.append(h, why, imp);
        ul.append(li);
      }
      panel.append(ul);
      panels.append(panel);
      tab.addEventListener("click", () => selectTab(cat));
      tab.addEventListener("keydown", (e) => onTabKey(e, cats));
    });
    if (cats.length) selectTab(cats[0], false);
  }

  function selectTab(cat, focus = true) {
    document.querySelectorAll(".tab").forEach((t) => {
      const on = t.id === `tab-${cat}`;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      if (on && focus) t.focus();
    });
    document.querySelectorAll("#panels [role=tabpanel]").forEach((p) => { p.hidden = p.id !== `panel-${cat}`; });
  }

  function onTabKey(e, cats) {
    const idx = cats.findIndex((c) => `tab-${c}` === e.currentTarget.id);
    let next = null;
    if (e.key === "ArrowRight") next = (idx + 1) % cats.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + cats.length) % cats.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = cats.length - 1;
    if (next !== null) { e.preventDefault(); selectTab(cats[next]); }
  }

  function render(d) {
    renderAqi(d);
    renderWindow(d.outdoor_window);
    $("coach-note").textContent = d.coach_note;
    $("ai-badge").textContent = d.ai_generated ? "AI-written" : "Standard summary";
    renderImpact(d.impact, d.actions);
    renderPlan(d.actions);
    $("disclaimer").textContent = d.disclaimer;
    $("source").textContent = `Data: ${d.data_source}.`;
    $("answer").textContent = "";
    const report = $("report");
    report.hidden = false;
    report.focus();
    report.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function setBusy(value, buttonId, label, busyLabel) {
    busy = value;
    const btn = $(buttonId);
    btn.disabled = value;
    btn.textContent = value ? busyLabel : label;
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (busy) return;
    if (!place) { setStatus("Please search and choose your city first.", true); $("city").focus(); return; }
    const km = Number($("km").value);
    if (!Number.isFinite(km) || km < 0 || km > 150) { setStatus("Commute distance must be between 0 and 150 km.", true); $("km").focus(); return; }
    setBusy(true, "submit-btn", "Get my air plan", "Building your plan...");
    setStatus("Fetching live air quality and building your plan...");
    try {
      const data = await api("/api/assist", { method: "POST", headers: { "Content-Type": "application/json" }, body: body() });
      setStatus("Your plan is ready.");
      render(data);
    } catch (err) {
      setStatus(err.message, true);
    } finally {
      setBusy(false, "submit-btn", "Get my air plan", "");
    }
  }

  async function onAsk(event) {
    event.preventDefault();
    if (busy || !place) return;
    const q = $("question").value.trim();
    if (q.length < 3) { $("answer").textContent = "Please type a question of at least 3 characters."; $("question").focus(); return; }
    setBusy(true, "ask-btn", "Ask", "Thinking...");
    $("answer").textContent = "";
    try {
      const data = await api("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: body({ question: q }) });
      $("answer").textContent = data.answer + (data.ai_generated ? "" : " (standard answer)");
    } catch (err) {
      $("answer").textContent = err.message;
    } finally {
      setBusy(false, "ask-btn", "Ask", "");
    }
  }

  api("/api/health")
    .then((h) => { $("ai-note").hidden = Boolean(h.ai_enabled); })
    .catch(() => { /* health is informational only */ });

  $("search-btn").addEventListener("click", searchPlaces);
  $("city").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); searchPlaces(); } });
  $("city").addEventListener("input", () => { place = null; $("chosen").textContent = ""; });
  $("locate-btn").addEventListener("click", useLocation);
  $("form").addEventListener("submit", onSubmit);
  $("ask-form").addEventListener("submit", onAsk);
})();
