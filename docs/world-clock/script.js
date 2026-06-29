const DEFAULT_ZONES = [
  "UTC",
  "America/New_York",
  "Europe/London",
  "Asia/Karachi",
  "Asia/Tokyo",
  "Australia/Sydney"
];

const humanLabel = (tz) => {
  const city = tz.split("/").pop()?.replaceAll("_", " ") ?? tz;
  if (tz === "UTC") return "UTC";
  return city;
};

const state = {
  zones: new Set(DEFAULT_ZONES),
  use24Hour: false
};

const clockList = document.getElementById("clockList");
const template = document.getElementById("clockItemTemplate");
const hourFormatToggle = document.getElementById("hourFormatToggle");
const timezoneSelect = document.getElementById("timezoneSelect");
const addZoneBtn = document.getElementById("addZoneBtn");

function buildTimeZoneOptions() {
  let supported = [];
  try {
    supported = Intl.supportedValuesOf("timeZone");
  } catch {
    supported = DEFAULT_ZONES;
  }

  for (const tz of supported) {
    const option = document.createElement("option");
    option.value = tz;
    option.textContent = `${humanLabel(tz)} (${tz})`;
    timezoneSelect.appendChild(option);
  }
}

function formatTimeForZone(tz) {
  return new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: !state.use24Hour,
    timeZone: tz,
    weekday: "short",
    month: "short",
    day: "2-digit"
  }).format(new Date());
}

function renderClocks() {
  clockList.innerHTML = "";

  for (const tz of state.zones) {
    const clone = template.content.cloneNode(true);
    const item = clone.querySelector(".clock-item");
    const zoneLabel = clone.querySelector(".zone-label");
    const zoneId = clone.querySelector(".zone-id");
    const time = clone.querySelector(".time");
    const removeBtn = clone.querySelector(".remove-btn");

    zoneLabel.textContent = humanLabel(tz);
    zoneId.textContent = tz;
    time.textContent = formatTimeForZone(tz);

    removeBtn.addEventListener("click", () => {
      state.zones.delete(tz);
      renderClocks();
    });

    item.dataset.tz = tz;
    clockList.appendChild(clone);
  }
}

function updateTimes() {
  const timeEls = clockList.querySelectorAll(".clock-item");
  for (const item of timeEls) {
    const tz = item.dataset.tz;
    const time = item.querySelector(".time");
    if (!tz || !time) continue;
    time.textContent = formatTimeForZone(tz);
  }
}

hourFormatToggle.addEventListener("change", (event) => {
  state.use24Hour = event.target.checked;
  updateTimes();
});

addZoneBtn.addEventListener("click", () => {
  const tz = timezoneSelect.value;
  if (!tz) return;
  state.zones.add(tz);
  renderClocks();
});

buildTimeZoneOptions();
renderClocks();
setInterval(updateTimes, 1000);
