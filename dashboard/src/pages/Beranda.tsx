import { useSummary } from "../lib/queries";
import { fmtRp, greeting, todayLabel } from "../lib/format";
import { Card, ErrorBox, Spinner } from "../components/ui";
import { ApiError } from "../lib/api";

function HeroMetric({ value, label, accent }: { value: string; label: string; accent?: boolean }) {
  return (
    <div>
      <p className={`tnum font-display text-xl font-extrabold leading-none ${accent ? "text-accent" : "text-white"}`}>
        {value}
      </p>
      <p className="mt-1 text-xs text-white/55">{label}</p>
    </div>
  );
}

export default function Beranda() {
  const { data, isLoading, error } = useSummary();

  return (
    <div className="space-y-5">
      <header>
        <p className="text-sm font-medium capitalize text-ink/55">{todayLabel()}</p>
        <h1 className="font-display text-2xl font-extrabold tracking-tight text-ink">{greeting()} 👋</h1>
      </header>

      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}

      {data && (
        <>
          {/* Signature: the day's takings, framed like a nota total — every
              metric the owner checks lives on this one ledger card. */}
          <section className="rounded-[24px] bg-ink p-5 text-white shadow-[0_8px_24px_rgba(12,31,23,0.18)]">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/55">Pendapatan hari ini</p>
            <p className="tnum mt-1 font-display text-[2.6rem] font-extrabold leading-none text-gold">
              {fmtRp(data.revenue_today)}
            </p>
            <div className="tear my-4 text-white" />
            <div className="grid grid-cols-3 gap-2">
              <HeroMetric value={String(data.orders_today)} label="Pesanan" />
              <HeroMetric value={String(data.messages_handled)} label="Dibalas otomatis" />
              <HeroMetric
                value={String(data.pending_orders)}
                label="Menunggu"
                accent={data.pending_orders > 0}
              />
            </div>
          </section>

          <section>
            <h2 className="mb-2 font-display text-base font-bold text-ink">Terlaris hari ini</h2>
            {data.top_products.length === 0 ? (
              <Card>
                <p className="text-sm text-ink/55">Belum ada penjualan hari ini. Pesanan yang masuk akan muncul di sini.</p>
              </Card>
            ) : (
              <Card className="!p-2">
                <ul>
                  {data.top_products.map((p, i) => (
                    <li
                      key={p.name}
                      className="flex items-center gap-3 px-2 py-2.5 not-last:border-b not-last:border-ink/[0.06]"
                    >
                      <span
                        className={`tnum grid h-7 w-7 shrink-0 place-items-center rounded-lg text-sm font-bold ${
                          i === 0 ? "bg-gold/20 text-[#9a7400]" : "bg-ink/5 text-ink/50"
                        }`}
                      >
                        {i + 1}
                      </span>
                      <span className="flex-1 truncate font-semibold text-ink">{p.name}</span>
                      <span className="tnum text-sm font-semibold text-ink/55">{p.count} terjual</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </section>
        </>
      )}
    </div>
  );
}
