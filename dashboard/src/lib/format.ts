/** Format a number as Indonesian Rupiah, e.g. 50000 -> "Rp 50.000". */
export function fmtRp(amount: number | null | undefined): string {
  const n = amount ?? 0;
  return "Rp " + Math.round(n).toLocaleString("id-ID");
}

/** Time-of-day greeting, plain text (no emoji — the UI adds tone). */
export function greeting(date = new Date()): string {
  const h = date.getHours();
  if (h < 11) return "Selamat pagi";
  if (h < 15) return "Selamat siang";
  if (h < 18) return "Selamat sore";
  return "Selamat malam";
}

/** Today as an Indonesian date label, e.g. "Senin, 22 Juni". */
export function todayLabel(date = new Date()): string {
  return date.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long" });
}
