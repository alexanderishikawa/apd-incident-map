import type { Filters, Incident } from "./types";

/** Parse offense datetime like "Wed, Jul-15-2026 22:00" → YYYY-MM-DD */
export function offenseDateKey(raw: string | null): string | null {
  if (!raw) return null;
  const m = raw.match(/([A-Za-z]{3})-(\d{2})-(\d{4})/);
  if (!m) return null;
  const months: Record<string, string> = {
    Jan: "01",
    Feb: "02",
    Mar: "03",
    Apr: "04",
    May: "05",
    Jun: "06",
    Jul: "07",
    Aug: "08",
    Sep: "09",
    Oct: "10",
    Nov: "11",
    Dec: "12",
  };
  const mm = months[m[1]];
  if (!mm) return null;
  return `${m[3]}-${mm}-${m[2]}`;
}

function selectedValues(sel: HTMLSelectElement): string[] {
  return Array.from(sel.selectedOptions).map((o) => o.value);
}

export function readFilters(): Filters {
  return {
    dateFrom: (document.getElementById("dateFrom") as HTMLInputElement).value,
    dateTo: (document.getElementById("dateTo") as HTMLInputElement).value,
    offenses: selectedValues(document.getElementById("offenses") as HTMLSelectElement),
    zips: selectedValues(document.getElementById("zips") as HTMLSelectElement),
    zones: selectedValues(document.getElementById("zones") as HTMLSelectElement),
    areas: selectedValues(document.getElementById("areas") as HTMLSelectElement),
    q: (document.getElementById("q") as HTMLInputElement).value.trim().toLowerCase(),
    showUngeocoded: (document.getElementById("showUngeocoded") as HTMLInputElement)
      .checked,
  };
}

export function fillSelect(id: string, values: string[]) {
  const sel = document.getElementById(id) as HTMLSelectElement;
  sel.innerHTML = "";
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  }
}

export function applyFilters(rows: Incident[], f: Filters): Incident[] {
  return rows.filter((r) => {
    const d = offenseDateKey(r.offense_datetime);
    if (f.dateFrom && (!d || d < f.dateFrom)) return false;
    if (f.dateTo && (!d || d > f.dateTo)) return false;
    if (f.offenses.length && !r.offenses.some((o) => f.offenses.includes(o))) {
      return false;
    }
    if (f.zips.length && (!r.zip || !f.zips.includes(r.zip))) return false;
    if (f.zones.length && (!r.district_zone || !f.zones.includes(r.district_zone))) {
      return false;
    }
    if (f.areas.length && (!r.area_command || !f.areas.includes(r.area_command))) {
      return false;
    }
    if (f.q) {
      const hay = [
        r.case_number,
        r.location_raw,
        r.address_raw,
        r.city,
        r.zip,
        ...(r.offenses || []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (!hay.includes(f.q)) return false;
    }
    return true;
  });
}
