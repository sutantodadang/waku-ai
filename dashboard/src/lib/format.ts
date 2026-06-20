/** Format a number as Indonesian Rupiah, e.g. 50000 -> "Rp 50.000". */
export function fmtRp(amount: number | null | undefined): string {
  const n = amount ?? 0;
  return "Rp " + Math.round(n).toLocaleString("id-ID");
}

export function greeting(date = new Date()): string {
  const h = date.getHours();
  if (h < 11) return "☀️ Selamat Pagi";
  if (h < 15) return "🌤️ Selamat Siang";
  if (h < 18) return "🌅 Selamat Sore";
  return "🌙 Selamat Malam";
}
