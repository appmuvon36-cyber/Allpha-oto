"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
type Row = { [key: string]: unknown };
const row = (v: unknown): Row => typeof v === "object" && v !== null && !Array.isArray(v) ? v as Row : {};
const list = (v: unknown): Row[] => Array.isArray(v) ? v.map(row) : [];
const text = (v: unknown, fallback = "—") => typeof v === "string" || typeof v === "number" ? String(v) : fallback;
const money = (v: unknown) => new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(Number(v ?? 0));
const date = (v: unknown) => typeof v === "string" && v ? new Date(v).toLocaleString("id-ID") : "Belum tersedia";
const labels: Record<string, string> = { pending_payment: "Menunggu pembayaran", payment_review: "Review pembayaran", paid: "Dibayar", processing: "Diproses", shipped: "Dikirim", delivered: "Diterima", cancelled: "Dibatalkan", return_requested: "Permintaan retur", returned: "Diretur", partially_returned: "Retur sebagian", verified: "Terverifikasi", rejected: "Ditolak", pending_review: "Menunggu review", refund_pending: "Menunggu refund", refunded: "Refund tercatat" };

export default function AdminOrderDetailPage() {
  const params = useParams<{ orderId: string }>();
  const orderId = params.orderId;
  const supabase = getSupabaseBrowserClient();
  const [token, setToken] = useState("");
  const [order, setOrder] = useState<Row | null>(null);
  const [items, setItems] = useState<Row[]>([]);
  const [payments, setPayments] = useState<Row[]>([]);
  const [returns, setReturns] = useState<Row[]>([]);
  const [events, setEvents] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (accessToken: string) => {
    setLoading(true); setError("");
    try {
      const response = await fetch(API + "/v1/orders/" + encodeURIComponent(orderId), { headers: { Authorization: "Bearer " + accessToken }, cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(text(row(body).detail, "Detail pesanan tidak dapat dimuat."));
      const data = row(body);
      setOrder(row(data.order)); setItems(list(data.items)); setPayments(list(data.payments)); setReturns(list(data.returns)); setEvents(list(data.fulfillment_events));
    } catch (e) { setError(e instanceof Error ? e.message : "Terjadi kesalahan saat memuat detail pesanan."); }
    finally { setLoading(false); }
  }, [orderId]);

  useEffect(() => {
    let alive = true;
    async function init() {
      if (!supabase) { setError("Supabase belum dikonfigurasi pada environment Admin."); setLoading(false); return; }
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();
      if (sessionError || !session) { window.location.assign("/login"); return; }
      const { data: profile, error: profileError } = await supabase.from("user_profiles").select("role,is_active").eq("id", session.user.id).maybeSingle();
      if (profileError || !profile?.is_active || !["admin", "order_manager"].includes(profile.role ?? "")) { setError("Akses detail pesanan memerlukan profil aktif dengan role admin atau order_manager."); setLoading(false); return; }
      if (alive) { setToken(session.access_token); await load(session.access_token); }
    }
    void init();
    return () => { alive = false; };
  }, [supabase, load]);

  const section = (title: string, subtitle: string, children: React.ReactNode) => <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white"><div className="border-b p-4"><h2 className="font-semibold">{title}</h2><p className="mt-1 text-sm text-slate-500">{subtitle}</p></div>{children}</section>;

  return <main className="min-h-screen bg-slate-50 text-slate-900"><header className="border-b bg-white"><div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-4 sm:px-6"><div className="flex items-center gap-3"><Link href="/inventory-orders" className="rounded-lg border p-2" aria-label="Kembali ke operasional"><ArrowLeft size={18}/></Link><div><p className="text-xs font-semibold uppercase tracking-wide text-orange-600">OtoClinic · Operasional</p><h1 className="text-lg font-bold sm:text-2xl">Detail & timeline pesanan</h1></div></div><button onClick={() => token && void load(token)} disabled={loading || !token} className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold disabled:opacity-50"><RefreshCw size={15}/> Refresh</button></div></header>
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 sm:px-6">
      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
      {loading && <div className="rounded-xl border bg-white p-8 text-sm text-slate-500">Memuat detail dari FastAPI…</div>}
      {!loading && order && <>
        {section("Ringkasan pesanan", "Nilai dan status berasal dari order kanonis di backend.", <div className="grid gap-4 p-4 sm:grid-cols-2"><div><p className="text-xs text-slate-500">Order UUID</p><p className="break-all font-mono text-sm">{text(order.id)}</p><p className="mt-3 text-xs text-slate-500">Customer UUID</p><p className="break-all font-mono text-sm">{text(order.customer_user_id)}</p><p className="mt-3 text-xs text-slate-500">Dibuat</p><p className="text-sm">{date(order.created_at)}</p></div><div><p className="text-xs text-slate-500">Status</p><p className="font-semibold">{labels[text(order.status, "")] ?? text(order.status)}</p><p className="mt-3 text-xs text-slate-500">Subtotal / ongkir / total</p><p className="text-sm">{money(order.subtotal)} / {money(order.shipping_fee)} / <strong>{money(order.total_amount)}</strong></p><p className="mt-3 text-xs text-slate-500">Kanal</p><p className="text-sm">{text(order.sales_channel, "web") === "whatsapp" ? "WhatsApp" : "Web"}</p><p className="mt-3 text-xs text-slate-500">Handoff WhatsApp</p><p className="text-sm">{text(order.whatsapp_handoff_status, "not_started")} · disiapkan {date(order.whatsapp_handoff_prepared_at)} · ditinjau {date(order.whatsapp_handoff_reviewed_at)}</p>{order.whatsapp_handoff_review_note && <p className="mt-1 text-sm text-slate-600">Catatan: {text(order.whatsapp_handoff_review_note)}</p>}</div></div>)}
        {section("Item pesanan", "Snapshot SKU, nama, kondisi, jumlah dan harga ketika order dibuat.", items.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50"><tr><th className="p-3">Produk</th><th className="p-3">SKU</th><th className="p-3">Kondisi</th><th className="p-3">Qty</th><th className="p-3">Harga</th><th className="p-3">Total</th></tr></thead><tbody>{items.map((it, i) => <tr key={text(it.id, String(i))} className="border-t"><td className="p-3">{text(it.name_snapshot)}</td><td className="p-3">{text(it.sku_snapshot)}</td><td className="p-3">{text(it.condition_snapshot)}</td><td className="p-3">{text(it.quantity)}</td><td className="p-3">{money(it.unit_price)}</td><td className="p-3 font-semibold">{money(it.line_total)}</td></tr>)}</tbody></table></div> : <p className="p-4 text-sm text-slate-500">Tidak ada item yang dapat dibaca.</p>)}
        {section("Timeline pengiriman", "Event timeline berasal dari catatan fulfillment; tidak ada tracking eksternal yang dikarang.", events.length ? <ol className="divide-y">{events.map((event, i) => <li key={text(event.id, String(i))} className="flex gap-3 p-4"><div className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-orange-500"/><div className="min-w-0"><p className="font-semibold">{text(event.event_type)}</p><p className="text-sm text-slate-600">{text(event.from_status, "—")} → {text(event.to_status, "—")}</p><p className="text-xs text-slate-500">{date(event.created_at)} · {text(event.carrier)} {text(event.service)} {text(event.tracking_code)}</p>{event.note && <p className="mt-1 break-words text-sm">{text(event.note)}</p>}</div></li>)}</ol> : <p className="p-4 text-sm text-slate-500">Belum ada event pengiriman.</p>)}
        {section("Pembayaran", "Catatan pembayaran dan review yang dapat dibaca oleh staf order.", payments.length ? <div className="divide-y">{payments.map((p, i) => <div key={text(p.id, String(i))} className="grid gap-2 p-4 sm:grid-cols-2"><div><p className="font-semibold">{text(p.event_type)} · {labels[text(p.status, "")] ?? text(p.status)}</p><p className="text-sm text-slate-500">{text(p.method)} · {date(p.created_at)}</p><p className="break-all text-xs text-slate-500">Referensi: {text(p.provider_reference)}</p></div><div><p className="font-semibold">{money(p.amount)}</p><p className="text-sm text-slate-600">Review: {text(p.review_note)}</p><p className="text-xs text-slate-500">Ditinjau {date(p.reviewed_at)}</p></div></div>)}</div> : <p className="p-4 text-sm text-slate-500">Belum ada event pembayaran.</p>)}
        {section("Retur & refund", "Status retur dan referensi refund tersimpan pada order.", returns.length ? <div className="divide-y">{returns.map((r, i) => <div key={text(r.id, String(i))} className="grid gap-2 p-4 sm:grid-cols-2"><div><p className="font-semibold">{labels[text(r.status, "")] ?? text(r.status)}</p><p className="text-sm">{text(r.reason)}</p><p className="text-xs text-slate-500">{date(r.created_at)}</p></div><div><p className="font-semibold">{money(r.requested_refund)}</p><p className="break-all text-xs text-slate-500">Referensi refund: {text(r.refund_provider_reference)}</p></div></div>)}</div> : <p className="p-4 text-sm text-slate-500">Belum ada permintaan retur.</p>)}
      </>}
      <p className="text-xs text-slate-500">Akses detail menggunakan sesi Supabase aktif dan API FastAPI. Tindakan transaksi tetap tersedia di kotak masuk operasional dan divalidasi server-side.</p>
    </div></main>;
}
