/* Customer pages: time-range filter and the slide-in booking panel. */
(function () {
  "use strict";

  const csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
  const MINUTE = 60000;

  /* ---------- Toast ---------- */
  const toastElement = document.getElementById("toast");
  let toastTimer = null;

  function showToast(message) {
    if (!toastElement) return;
    toastElement.textContent = message;
    toastElement.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastElement.classList.remove("show"), 4000);
  }

  if (typeof flatpickr === "undefined") return;

  /* ---------- Browse time-range filter ---------- */
  ["filter-from", "filter-to"].forEach((id) => {
    const input = document.getElementById(id);
    if (input) {
      flatpickr(input, {
        enableTime: true,
        minuteIncrement: 30,
        dateFormat: "Y-m-d H:i",
        altInput: true,
        altFormat: "M j, Y h:i K",
      });
    }
  });

  /* ---------- Booking panel ---------- */
  const panel = document.getElementById("booking-panel");
  if (!panel || !window.CUSTOMER_URLS) return;

  const byId = (id) => document.getElementById(id);
  const ui = {
    backdrop: byId("panel-backdrop"),
    title: byId("panel-title"),
    rate: byId("panel-rate"),
    error: byId("panel-error"),
    startWrap: byId("start-slots-wrap"),
    startSlots: byId("start-slots"),
    endSection: byId("end-section"),
    endTitle: byId("end-day-title"),
    endWrap: byId("end-slots-wrap"),
    endSlots: byId("end-slots"),
    summary: byId("panel-summary"),
    submit: byId("panel-submit"),
  };

  const state = {
    id: null, name: "", unit: "DAY", rate: 0, minDuration: 1440, bookable: false,
    now: new Date(), blocked: [], startDay: null, start: null, end: null,
  };
  let startCalendar = null;
  let endCalendar = null;

  const pad = (n) => String(n).padStart(2, "0");
  const toServer = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  function fromServer(text) {
    const [date, time] = text.split(" ");
    const [y, m, d] = date.split("-").map(Number);
    const [h, min] = time.split(":").map(Number);
    return new Date(y, m - 1, d, h, min);
  }
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const timeLabel = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const dateTimeLabel = (d) => d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });

  function slotsOf(day) {
    const slots = [];
    for (let i = 0; i < 48; i += 1) {
      slots.push(new Date(day.getFullYear(), day.getMonth(), day.getDate(), 0, i * 30));
    }
    return slots;
  }

  /* ---------- Availability rules (the server re-checks every request) ---------- */
  const isFree = (from, to) => !state.blocked.some((b) => b.start < to && b.end > from);
  const startAllowed = (slot) => slot >= state.now && isFree(slot, new Date(slot.getTime() + state.minDuration * MINUTE));

  function summarize(allowed, slots) {
    const count = slots.filter(allowed).length;
    if (count === 0) return "none";
    return count === slots.length ? "free" : "partial";
  }

  function startDayState(day) {
    return state.bookable ? summarize(startAllowed, slotsOf(day)) : "none";
  }

  // The rental may not run into the next reservation that starts after the chosen start.
  function endLimit() {
    let limit = null;
    state.blocked.forEach((b) => {
      if (b.start >= state.start && (limit === null || b.start < limit)) limit = b.start;
    });
    return limit;
  }

  const hourEndAllowed = (slot) => {
    const limit = endLimit();
    return slot > state.start && (limit === null || slot <= limit);
  };

  // Day-rate items end a whole number of days later at the same time of day.
  function dayEndFor(day) {
    return new Date(day.getFullYear(), day.getMonth(), day.getDate(), state.start.getHours(), state.start.getMinutes());
  }

  function endDayState(day) {
    if (!state.start) return "none";
    if (state.unit === "HOUR") return summarize(hourEndAllowed, slotsOf(day));
    const candidate = dayEndFor(day);
    const days = Math.round((startOfDay(candidate) - startOfDay(state.start)) / 86400000);
    const limit = endLimit();
    return days >= 1 && (limit === null || candidate <= limit) ? "free" : "none";
  }

  /* ---------- Messages ---------- */
  function showError(message) {
    ui.error.textContent = message;
    ui.error.hidden = false;
  }
  function hideError() {
    ui.error.hidden = true;
  }

  /* ---------- Rendering ---------- */
  function renderSlots(container, slots, allowed, selected, onPick) {
    container.textContent = "";
    slots.forEach((slot) => {
      const ok = allowed(slot);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "slot";
      button.textContent = timeLabel(slot);
      if (!ok) {
        button.classList.add("unavailable");
        button.setAttribute("aria-disabled", "true");
      }
      if (selected && selected.getTime() === slot.getTime()) button.classList.add("selected");
      button.addEventListener("click", () => {
        if (!ok) {
          showError("That time is not available. It may already be reserved, or it is in the past.");
          return;
        }
        hideError();
        onPick(slot);
      });
      container.appendChild(button);
    });
  }

  function updateSummary() {
    if (!(state.start && state.end)) {
      ui.summary.hidden = true;
      ui.submit.disabled = true;
      return;
    }
    const minutes = Math.round((state.end - state.start) / MINUTE);
    const price = state.unit === "DAY" ? state.rate * Math.round(minutes / 1440) : (state.rate * minutes) / 60;
    ui.summary.textContent = `${dateTimeLabel(state.start)} to ${dateTimeLabel(state.end)} \u00b7 estimated $${price.toFixed(2)}`;
    ui.summary.hidden = false;
    ui.submit.disabled = false;
  }

  function dayHook(stateOf, unavailableMessage) {
    return (selectedDates, dateStr, instance, dayElement) => {
      const status = stateOf(dayElement.dateObj);
      if (status === "free") dayElement.classList.add("day-free");
      if (status === "partial") {
        dayElement.classList.add("day-partial");
        dayElement.title = "Partly available";
      }
      if (status === "none") dayElement.addEventListener("click", () => showError(unavailableMessage));
    };
  }

  function ensureCalendars() {
    if (startCalendar) return;
    const common = { inline: true, monthSelectorType: "static", disableMobile: true };
    startCalendar = flatpickr("#start-day", {
      ...common,
      disable: [(date) => startDayState(date) === "none"],
      onDayCreate: dayHook(startDayState, "No start times are available on that day."),
      onChange: (dates) => {
        if (!dates.length) return;
        state.startDay = dates[0];
        resetSelection(false);
        renderStart();
      },
    });
    endCalendar = flatpickr("#end-day", {
      ...common,
      disable: [(date) => endDayState(date) === "none"],
      onDayCreate: dayHook(endDayState, "That day cannot be your end day for this start time."),
      onChange: (dates) => {
        if (!dates.length || !state.start) return;
        if (state.unit === "HOUR") {
          state.end = null;
          renderEnd(dates[0]);
        } else {
          state.end = dayEndFor(dates[0]);
        }
        updateSummary();
      },
    });
  }

  function renderStart() {
    ui.startWrap.hidden = false;
    renderSlots(ui.startSlots, slotsOf(state.startDay), startAllowed, state.start, pickStart);
  }

  function renderEnd(day) {
    ui.endWrap.hidden = false;
    renderSlots(ui.endSlots, slotsOf(day), hourEndAllowed, state.end, (slot) => {
      state.end = slot;
      renderEnd(day);
      updateSummary();
    });
  }

  function pickStart(slot) {
    state.start = slot;
    state.end = null;
    renderStart();
    ui.endSection.hidden = false;
    ui.endWrap.hidden = true;
    ui.endTitle.textContent = state.unit === "DAY" ? "2. End day (same time of day)" : "2. End day";
    endCalendar.clear(false);
    endCalendar.redraw();
    endCalendar.jumpToDate(slot);
    if (state.unit === "HOUR") {
      for (let i = 0; i < 90; i += 1) {
        const day = new Date(slot.getFullYear(), slot.getMonth(), slot.getDate() + i);
        if (endDayState(day) !== "none") {
          endCalendar.setDate(day, true);
          break;
        }
      }
    }
    updateSummary();
  }

  function resetSelection(clearDay) {
    state.start = null;
    state.end = null;
    if (clearDay) state.startDay = null;
    ui.endSection.hidden = true;
    ui.endWrap.hidden = true;
    if (clearDay) ui.startWrap.hidden = true;
    updateSummary();
  }

  /* ---------- Loading and opening ---------- */
  async function loadAvailability() {
    const url = window.CUSTOMER_URLS.availability.replace("/0/", `/${state.id}/`);
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "Could not load availability.");
    state.unit = data.rate_unit;
    state.rate = Number(data.rate);
    state.minDuration = data.rate_unit === "DAY" ? 1440 : 30;
    state.now = fromServer(data.now);
    state.blocked = data.blocked.map(([s, e]) => ({ start: fromServer(s), end: fromServer(e) }));
    state.bookable = data.bookable && !data.in_cart;
    ui.rate.textContent = `$${state.rate.toFixed(2)} per ${state.unit === "DAY" ? "day" : "hour"}`
      + (state.unit === "DAY" ? " \u00b7 rented in whole 24-hour days" : " \u00b7 30-minute increments");

    ensureCalendars();
    resetSelection(true);
    startCalendar.clear(false);
    endCalendar.clear(false);
    startCalendar.redraw();
    startCalendar.jumpToDate(state.now);
    if (!data.bookable) showError(data.reason);
    else if (data.in_cart) showError("This equipment is already in your cart.");
  }

  async function openPanel(id, name) {
    state.id = id;
    state.name = name;
    ui.title.textContent = `Rent: ${name}`;
    hideError();
    panel.classList.add("open");
    ui.backdrop.classList.add("open");
    panel.setAttribute("aria-hidden", "false");
    ui.title.focus();
    try {
      await loadAvailability();
    } catch (error) {
      showError(error.message);
    }
  }

  function closePanel() {
    panel.classList.remove("open");
    ui.backdrop.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
  }

  document.querySelectorAll(".add-to-cart").forEach((button) => {
    button.addEventListener("click", () => openPanel(button.dataset.equipmentId, button.dataset.name));
  });
  byId("panel-close").addEventListener("click", closePanel);
  ui.backdrop.addEventListener("click", closePanel);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closePanel();
  });

  ui.submit.addEventListener("click", async () => {
    hideError();
    ui.submit.disabled = true;
    try {
      const response = await fetch(window.CUSTOMER_URLS.add, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: JSON.stringify({ equipment_id: state.id, start: toServer(state.start), end: toServer(state.end) }),
      });
      const data = await response.json().catch(() => ({ ok: false, error: "Unexpected response from the server." }));
      if (data.ok) {
        closePanel();
        const counter = byId("cart-count");
        if (counter) counter.textContent = data.cart_count;
        showToast(`${state.name} was added to your cart.`);
      } else {
        // Reload so the calendar reflects whatever just changed, then keep the message visible.
        const message = data.error || "The item could not be added.";
        await loadAvailability().catch(() => {});
        showError(message);
      }
    } catch (error) {
      showError("Could not reach the server. Try again.");
      updateSummary();
    }
  });
})();
