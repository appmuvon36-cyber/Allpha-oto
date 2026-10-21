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
  const [communications, setCommunications] = useState<Row[]>([]);
  const [commChannel, setCommChannel] = useState("whatsapp");
  const [commDirection, setCommDirection] = useState("outbound");
  const [commOutcome, setCommOutcome] = useState("attempted");
  const [commSummary, setCommSummary] = useState("");
  const [commReference, setCommReference] = useState("");
  const [commSaving, setCommSaving] = useState(false);
  const [quoteAmount, setQuoteAmount] = useState("");
  const [quoteCarrier, setQuoteCarrier] = useState("");
  const [quoteService, setQuoteService] = useState("");
  const [quoteNote, setQuoteNote] = useState("");
  const [quoteSaving, setQuoteSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (accessToken: string) => {
    setLoading(true); setError("");
    try {
      const response = await fetch(API + "/v1/orders/" + encodeURIComponent(orderId), { headers: { Authorization: "Bearer " + accessToken }, cache: "no-store" });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(text(row(body).detail, "Detail pesanan tidak dapat dimuat."));
      const data = row(body);
      const communicationResponse = await fetch(API + "/v1/admin/orders/" + encodeURIComponent(orderId) + "/communications?limit=100&offset=0", { headers: { Authorization: "Bearer " + accessToken }, cache: "no-store" });
      const communicationBody = await communicationResponse.json().catch(() => ({}));
      if (!communicationResponse.ok) throw new Error(text(row(communicationBody).detail, "Riwayat komunikasi tidak dapat dimuat."));
      setOrder(row(data.order)); setItems(list(data.items)); setPayments(list(data.payments)); setReturns(list(data.returns)); setEvents(list(data.fulfillment_events)); setCommunications(list(row(communicationBody).items));
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

  async function submitManualQuote(event: import("react").FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !quoteCarrier.trim() || !quoteService.trim() || !quoteNote.trim()) return;
    const amount = Number(quoteAmount);
    if (!Number.isSafeInteger(amount) || amount < 0 || amount > 1_000_000_000) {
      setError("Ongkir manual harus bilangan rupiah bulat antara Rp0 dan Rp1.000.000.000.");
      return;
    }
    if (!window.confirm("Simpan ongkir manual dan perbarui total pesanan? Aksi hanya diizinkan sebelum pembayaran dimulai dan selama reservasi stok masih aktif.")) return;
    setQuoteSaving(true); setError("");
    try {
      const response = await fetch(API + "/v1/admin/orders/" + encodeURIComponent(orderId) + "/manual-shipping-quote", {
        method: "POST",
        headers: { Authorization: "Bearer " + token, "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ amount, carrier: quoteCarrier.trim(), service: quoteService.trim(), note: quoteNote.trim() }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(text(row(body).detail, "Ongkir manual tidak dapat disimpan."));
      setQuoteAmount(""); setQuoteCarrier(""); setQuoteService(""); setQuoteNote("");
      await load(token);
    } catch (e) { setError(e instanceof Error ? e.message : "Ongkir manual gagal disimpan."); }
    finally { setQuoteSaving(false); }
  }

  async function addCommunication(event: import("react").FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || commSummary.trim().length < 2) return;
    setCommSaving(true); setError("");
    try {
      const response = await fetch(API + "/v1/admin/orders/" + encodeURIComponent(orderId) + "/communications", {
        method: "POST",
        headers: { Authorization: "Bearer " + token, "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ channel: commChannel, direction: commDirection, outcome: commOutcome, summary: commSummary.trim(), ...(commReference.trim() ? { external_reference: commReference.trim() } : {}) }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(text(row(body).detail, "Catatan komunikasi tidak dapat disimpan."));
      setCommSummary(""); setCommReference("");
      await load(token);
    } catch (e) { setError(e instanceof Error ? e.message : "Catatan komunikasi gagal disimpan."); }
    finally { setCommSaving(false); }
  }

  const section = (title: string, subtitle: string, children: React.ReactNode) => <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white"><div className="border-b p-4"><h2 className="font-semibold">{title}</h2><p className="mt-1 text-sm text-slate-500">{subtitle}</p></div>{children}</section>;

  return <main className="min-h-screen bg-slate-50 text-slate-900"><header className="border-b bg-white"><div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-4 sm:px-6"><div className="flex items-center gap-3"><Link href="/inventory-orders" className="rounded-lg border p-2" aria-label="Kembali ke operasional"><ArrowLeft size={18}/></Link><div><p className="text-xs font-semibold uppercase tracking-wide text-orange-600">OtoClinic · Operasional</p><h1 className="text-lg font-bold sm:text-2xl">Detail & timeline pesanan</h1></div></div><button onClick={() => token && void load(token)} disabled={loading || !token} className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold disabled:opacity-50"><RefreshCw size={15}/> Refresh</button></div></header>
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-6 sm:px-6">
      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
      {loading && <div className="rounded-xl border bg-white p-8 text-sm text-slate-500">Memuat detail dari FastAPI…</div>}
      {!loading && order && <>
        {section("Ringkasan pesanan", "Nilai dan status berasal dari order kanonis di backend.", <div className="grid gap-4 p-4 sm:grid-cols-2"><div><p className="text-xs text-slate-500">Order UUID</p><p className="break-all font-mono text-sm">{text(order.id)}</p><p className="mt-3 text-xs text-slate-500">Customer UUID</p><p className="break-all font-mono text-sm">{text(order.customer_user_id)}</p><p className="mt-3 text-xs text-slate-500">Dibuat</p><p className="text-sm">{date(order.created_at)}</p></div><div><p className="text-xs text-slate-500">Status</p><p className="font-semibold">{labels[text(order.status, "")] ?? text(order.status)}</p><p className="mt-3 text-xs text-slate-500">Subtotal / ongkir / total</p><p className="text-sm">{money(order.subtotal)} / {money(order.shipping_fee)} / <strong>{money(order.total_amount)}</strong></p><p className="mt-3 text-xs text-slate-500">Kanal</p><p className="text-sm">{text(order.sales_channel, "web") === "whatsapp" ? "WhatsApp" : "Web"}</p><p className="mt-3 text-xs text-slate-500">Handoff WhatsApp</p><p className="text-sm">{text(order.whatsapp_handoff_status, "not_started")} · disiapkan {date(order.whatsapp_handoff_prepared_at)} · ditinjau {date(order.whatsapp_handoff_reviewed_at)}</p>{Boolean(order.whatsapp_handoff_review_note) && <p className="mt-1 text-sm text-slate-600">Catatan: {text(order.whatsapp_handoff_review_note)}</p>}</div></div>)}
        {order.status === "pending_payment" && <section className="overflow-hidden rounded-2xl border border-amber-200 bg-white"><div className="border-b border-amber-200 bg-amber-50 p-4"><h2 className="font-semibold text-amber-950">Tetapkan ongkir manual</h2><p className="mt-1 text-sm text-amber-900">Total akan dihitung server dari subtotal − diskon + ongkir. Hanya untuk pesanan belum dibayar tanpa payment event/intent dan dengan reservasi stok aktif. Berlaku hingga reservasi terdekat kedaluwarsa. Sistem tidak mengirim notifikasi; hubungi pelanggan dan catat kontak di Riwayat komunikasi.</p></div><form onSubmit={submitManualQuote} className="grid gap-3 p-4 sm:grid-cols-2"><label className="text-sm font-medium">Ongkir (IDR)<input required type="number" min="0" max="1000000000" step="1" value={quoteAmount} onChange={e=>setQuoteAmount(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5 font-normal" placeholder="Contoh: 25000"/></label><label className="text-sm font-medium">Kurir<input required maxLength={80} value={quoteCarrier} onChange={e=>setQuoteCarrier(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5 font-normal" placeholder="Kurir / pengiriman manual"/></label><label className="text-sm font-medium">Layanan<input required maxLength={80} value={quoteService} onChange={e=>setQuoteService(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5 font-normal" placeholder="Layanan yang disepakati"/></label><label className="text-sm font-medium">Alasan / catatan quote<input required minLength={2} maxLength={1000} value={quoteNote} onChange={e=>setQuoteNote(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5 font-normal" placeholder="Alasan tarif manual dan sumber konfirmasi"/></label><button disabled={quoteSaving||!quoteCarrier.trim()||!quoteService.trim()||!quoteNote.trim()||quoteAmount===""} className="w-fit rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{quoteSaving?"Menyimpan…":"Simpan ongkir manual"}</button></form></section>}
        {section("Item pesanan", "Snapshot SKU, nama, kondisi, jumlah dan harga ketika order dibuat.", items.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50"><tr><th className="p-3">Produk</th><th className="p-3">SKU</th><th className="p-3">Kondisi</th><th className="p-3">Qty</th><th className="p-3">Harga</th><th className="p-3">Total</th></tr></thead><tbody>{items.map((it, i) => <tr key={text(it.id, String(i))} className="border-t"><td className="p-3">{text(it.name_snapshot)}</td><td className="p-3">{text(it.sku_snapshot)}</td><td className="p-3">{text(it.condition_snapshot)}</td><td className="p-3">{text(it.quantity)}</td><td className="p-3">{money(it.unit_price)}</td><td className="p-3 font-semibold">{money(it.line_total)}</td></tr>)}</tbody></table></div> : <p className="p-4 text-sm text-slate-500">Tidak ada item yang dapat dibaca.</p>)}
        {section("Timeline pengiriman", "Event timeline berasal dari catatan fulfillment; tidak ada tracking eksternal yang dikarang.", events.length ? <ol className="divide-y">{events.map((event, i) => <li key={text(event.id, String(i))} className="flex gap-3 p-4"><div className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-orange-500"/><div className="min-w-0"><p className="font-semibold">{text(event.event_type)}</p><p className="text-sm text-slate-600">{text(event.from_status, "—")} → {text(event.to_status, "—")}</p><p className="text-xs text-slate-500">{date(event.created_at)} · {text(event.carrier)} {text(event.service)} {text(event.tracking_code)}</p>{Boolean(event.note) && <p className="mt-1 break-words text-sm">{text(event.note)}</p>}</div></li>)}</ol> : <p className="p-4 text-sm text-slate-500">Belum ada event pengiriman.</p>)}
        {section("Pembayaran", "Catatan pembayaran dan review yang dapat dibaca oleh staf order.", payments.length ? <div className="divide-y">{payments.map((p, i) => <div key={text(p.id, String(i))} className="grid gap-2 p-4 sm:grid-cols-2"><div><p className="font-semibold">{text(p.event_type)} · {labels[text(p.status, "")] ?? text(p.status)}</p><p className="text-sm text-slate-500">{text(p.method)} · {date(p.created_at)}</p><p className="break-all text-xs text-slate-500">Referensi: {text(p.provider_reference)}</p></div><div><p className="font-semibold">{money(p.amount)}</p><p className="text-sm text-slate-600">Review: {text(p.review_note)}</p><p className="text-xs text-slate-500">Ditinjau {date(p.reviewed_at)}</p></div></div>)}</div> : <p className="p-4 text-sm text-slate-500">Belum ada event pembayaran.</p>)}
        {section("Riwayat komunikasi pelanggan", "Log manual yang diaudit. Mencatat kontak tidak mengirim pesan dan tidak membuktikan pesan terkirim/diterima.", <div><form onSubmit={addCommunication} className="grid gap-3 border-b bg-slate-50 p-4 sm:grid-cols-2"><label className="text-sm font-medium">Kanal<select value={commChannel} onChange={e=>setCommChannel(e.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2.5 font-normal"><option value="whatsapp">WhatsApp</option><option value="phone">Telepon</option><option value="email">Email</option><option value="internal_note">Catatan internal</option></select></label><label className="text-sm font-medium">Arah<select value={commDirection} onChange={e=>setCommDirection(e.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2.5 font-normal"><option value="outbound">Keluar ke pelanggan</option><option value="inbound">Masuk dari pelanggan</option><option value="internal">Internal</option></select></label><label className="text-sm font-medium">Hasil<select value={commOutcome} onChange={e=>setCommOutcome(e.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2.5 font-normal"><option value="planned">Direncanakan</option><option value="attempted">Dicoba</option><option value="sent">Dicatat terkirim manual</option><option value="received">Dicatat diterima manual</option><option value="failed">Gagal</option><option value="not_sent">Tidak dikirim</option></select></label><label className="text-sm font-medium">Referensi eksternal (opsional)<input value={commReference} onChange={e=>setCommReference(e.target.value)} maxLength={300} className="mt-1 w-full rounded-lg border bg-white p-2.5 font-normal" placeholder="ID tiket atau referensi percakapan"/></label><label className="text-sm font-medium sm:col-span-2">Ringkasan komunikasi<textarea required minLength={2} maxLength={2000} value={commSummary} onChange={e=>setCommSummary(e.target.value)} className="mt-1 w-full rounded-lg border bg-white p-2.5 font-normal" rows={3} placeholder="Ringkasan faktual; hindari data pembayaran atau data pribadi yang tidak diperlukan."/></label><button disabled={commSaving||commSummary.trim().length<2} className="w-fit rounded-lg bg-orange-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{commSaving?"Menyimpan…":"Simpan catatan komunikasi"}</button></form>{communications.length ? <ol className="divide-y">{communications.map((c,i)=><li key={text(c.id,String(i))} className="p-4"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{text(c.channel)}</span><span className="text-sm text-slate-500">{text(c.direction)} · {text(c.outcome)}</span><span className="text-xs text-slate-500">{date(c.created_at)}</span></div><p className="mt-2 whitespace-pre-wrap break-words text-sm">{text(c.summary)}</p>{Boolean(c.external_reference)&&<p className="mt-1 break-all text-xs text-slate-500">Referensi: {text(c.external_reference)}</p>}<p className="mt-1 break-all text-xs text-slate-500">Dicatat oleh: {text(c.actor_user_id)}</p></li>)}</ol> : <p className="p-4 text-sm text-slate-500">Belum ada catatan komunikasi untuk pesanan ini.</p>}</div>)}
        {section("Retur & refund", "Status retur dan referensi refund tersimpan pada order.", returns.length ? <div className="divide-y">{returns.map((r, i) => <div key={text(r.id, String(i))} className="grid gap-2 p-4 sm:grid-cols-2"><div><p className="font-semibold">{labels[text(r.status, "")] ?? text(r.status)}</p><p className="text-sm">{text(r.reason)}</p><p className="text-xs text-slate-500">{date(r.created_at)}</p></div><div><p className="font-semibold">{money(r.requested_refund)}</p><p className="break-all text-xs text-slate-500">Referensi refund: {text(r.refund_provider_reference)}</p></div></div>)}</div> : <p className="p-4 text-sm text-slate-500">Belum ada permintaan retur.</p>)}
      </>}
      <p className="text-xs text-slate-500">Akses detail menggunakan sesi Supabase aktif dan API FastAPI. Tindakan transaksi tetap tersedia di kotak masuk operasional dan divalidasi server-side.</p>
    </div></main>;
}
