import { useBookings, useUpdateBooking, useRemindBooking, useSendBookingPayment } from "../lib/queries";
import { fmtRp } from "../lib/format";
import { ApiError } from "../lib/api";
import { Button, Card, ErrorBox, PageTitle, Spinner } from "../components/ui";
import type { Booking } from "../lib/types";

const STATUS_LABEL: Record<string, string> = {
  requested: "Menunggu",
  confirmed: "Dikonfirmasi",
  rejected: "Ditolak",
  completed: "Selesai",
  cancelled: "Dibatalkan",
};

const STATUS_BADGE: Record<string, string> = {
  requested: "bg-gold/15 text-[#9a7400]",
  confirmed: "bg-brand-tint text-brand-deep",
  rejected: "bg-red-50 text-red-600",
  completed: "bg-blue-50 text-blue-700",
  cancelled: "bg-ink/5 text-ink/50",
};

function fmtScheduled(s: string | null): string {
  if (!s) return "(waktu menyusul)";
  return new Date(s).toLocaleString("id-ID", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function isTomorrow(s: string | null): boolean {
  if (!s) return false;
  const d = new Date(s);
  const tom = new Date();
  tom.setDate(tom.getDate() + 1);
  return (
    d.getFullYear() === tom.getFullYear() &&
    d.getMonth() === tom.getMonth() &&
    d.getDate() === tom.getDate()
  );
}

function BookingCard({ b }: { b: Booking }) {
  const upd = useUpdateBooking();
  const remind = useRemindBooking();
  const sendPay = useSendBookingPayment();

  const set = (status: string) => upd.mutate({ id: b.id, d: { status } });

  return (
    <Card>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-bold text-ink">{b.customer_name}</p>
          <p className="mt-0.5 text-xs text-ink/45">
            #{b.id} • {fmtScheduled(b.scheduled_at)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {b.clash && (
            <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs font-semibold text-red-600">
              ⚠ Bentrok
            </span>
          )}
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_BADGE[b.status] ?? "bg-ink/5 text-ink/60"}`}
          >
            {STATUS_LABEL[b.status] ?? b.status}
          </span>
        </div>
      </div>

      <p className="tnum mt-2 text-xl font-extrabold text-ink">{fmtRp(b.total)}</p>
      {b.deposit_amount != null && b.deposit_amount > 0 && (
        <p className="text-xs text-ink/50">Deposit: {fmtRp(b.deposit_amount)}</p>
      )}

      {b.items.length > 0 && (
        <ul className="mt-2 space-y-0.5 border-t border-ink/[0.06] pt-2">
          {b.items.map((it, i) => (
            <li key={i} className="flex justify-between text-sm text-ink/60">
              <span className="truncate">
                {it.name}
                {it.duration_minutes ? (
                  <span className="text-ink/40"> · {it.duration_minutes} menit</span>
                ) : null}
              </span>
              <span className="tnum shrink-0 pl-2">{fmtRp(it.price)}</span>
            </li>
          ))}
        </ul>
      )}

      {b.notes && <p className="mt-2 text-xs italic text-ink/45">{b.notes}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        {b.status === "requested" && (
          <>
            <Button onClick={() => set("confirmed")} disabled={upd.isPending}>
              Konfirmasi
            </Button>
            <Button variant="danger" onClick={() => set("rejected")} disabled={upd.isPending}>
              Tolak
            </Button>
          </>
        )}
        {b.status === "confirmed" && (
          <>
            <Button onClick={() => set("completed")} disabled={upd.isPending}>
              Selesai
            </Button>
            <Button variant="danger" onClick={() => set("cancelled")} disabled={upd.isPending}>
              Batal
            </Button>
            <Button
              variant="ghost"
              onClick={() => sendPay.mutate(b.id)}
              disabled={sendPay.isPending}
            >
              {sendPay.isPending ? "..." : "Kirim bayar"}
            </Button>
          </>
        )}
        {(b.status === "requested" || b.status === "confirmed") && (
          <Button
            variant="ghost"
            onClick={() => remind.mutate(b.id)}
            disabled={remind.isPending}
          >
            {remind.isPending ? "..." : "Ingatkan"}
          </Button>
        )}
      </div>
    </Card>
  );
}

export default function Bookings() {
  const { data, isLoading, error } = useBookings();

  const tomorrow = data?.filter((b) => isTomorrow(b.scheduled_at)) ?? [];
  const all = data ?? [];

  return (
    <div>
      <PageTitle>Booking</PageTitle>

      {isLoading && <Spinner />}
      {error && <ErrorBox message={(error as ApiError).message} />}

      {tomorrow.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink/45">Besok</h2>
          <div className="space-y-3">
            {tomorrow.map((b) => (
              <BookingCard key={b.id} b={b} />
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-ink/45">Semua Booking</h2>
        {all.length === 0 && !isLoading && (
          <Card>
            <p className="text-sm text-ink/55">Belum ada booking.</p>
          </Card>
        )}
        <div className="space-y-3">
          {all.map((b) => (
            <BookingCard key={b.id} b={b} />
          ))}
        </div>
      </section>
    </div>
  );
}
