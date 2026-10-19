"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Boxes, ClipboardCheck, CreditCard, PackageCheck, RefreshCw, RotateCcw, Truck } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
type Row = Record<string, any>;
type Tab = "inventory" | "orders" | "payments" | "returns";

const money = (value: unknown) => new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(Number(value ?? 0));
const label: Record<string, string> = {
  pending_payment: "Menunggu pembayaran", payment_review: "Review pembayaran", paid: "Dibayar",
  processing: "Diproses", shipped: "Dikirim", delivered: "Diterima", cancelled: "Dibatalkan",
  return_requested: "Permintaan retur", returned: "Diretur", partially_returned: "Retur sebagian",
  pending_review: "Menunggu review", verified: "Terverifikasi", rejected: "Ditolak",
  requested: "Diajukan", approved: "Disetujui", received: "Diterima gudang", refund_pending: "Menunggu refund",
  refunded: "Refund tercatat",
};

export default function InventoryOrdersPage() {
  const supabase = getSupabaseBrowserClient();
  const [tab, setTab] = useState<Tab>("inventory");
  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [inventory, setInventory] = useState<Row[]>([]);
  const [orders, setOrders] = useState<Row[]>([]);
  const [payments, setPayments] = useState<Row[]>([]);
  const [returns, setReturns] = useState<Row[]>([]);
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState("");
  const [movement, setMovement] = useState("receipt");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const api = useCallback(async (path: string, init: RequestInit = {}) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", "Bearer " + token);
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const response = await fetch(API + path, { ...init, headers, cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail ?? "Permintaan gagal (HTTP " + response.status + ").");
    return body;
  }, [token]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    if (!supabase) { setError("Supabase belum dikonfigurasi pada environment Admin."); setLoading(false); return; }
    const { data: { session }, error: authError } = await supabase.auth.getSession();
    if (authError || !session) { window.location.assign("/login"); return; }
    setToken(session.access_token);
    const { data: profile, error: profileError } = await supabase.from("user_profiles").select("role,is_active").eq("id", session.user.id).maybeSingle();
    if (profileError || !profile?.is_active || !["admin", "inventory_manager", "order_manager"].includes(profile.role ?? "")) {
      setError("Akses memerlukan profil operasional aktif dengan role inventory_manager, order_manager, atau admin.");
      setLoading(false); return;
    }
    setRole(profile.role);
    const headers = { Authorization: "Bearer " + session.access_token };
    const paths = [
      fetch(API + "/v1/admin/inventory?limit=100", { headers, cache: "no-store" }),
      fetch(API + "/v1/admin/orders?limit=100", { headers, cache: "no-store" }),
      fetch(API + "/v1/admin/payments?status=pending_review&limit=100", { headers, cache: "no-store" }),
      fetch(API + "/v1/admin/returns?status=requested&limit=100", { headers, cache: "no-store" }),
    ];
    const responses = await Promise.all(paths);
    const bodies = await Promise.all(responses.map(async r => ({ ok: r.ok, status: r.status, body: await r.json().catch(() => ({})) })));
    const failed = bodies.find(x => !x.ok);
    if (failed) { setError("Queue transaksi tidak dapat dimuat (HTTP " + failed.status + "). Pastikan API, role, dan kebijakan RLS tersedia."); setLoading(false); return; }
    setInventory(bodies[0].body.items ?? []);
    setOrders(bodies[1].body.items ?? []);
    setPayments(bodies[2].body.items ?? []);
    setReturns(bodies[3].body.items ?? []);
    setLoading(false);
  }, [supabase]);

  useEffect(() => { void load(); }, [load]);

  async function mutate(path: string, action: string, payload: Row = {}) {
    if (!window.confirm("Konfirmasi aksi " + action + "? Perubahan transaksi akan dicatat ke audit.")) return;
    setBusy(action); setError(""); setNotice("");
    try {
      await api(path, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ action, payload }) });
      setNotice("Aksi " + action + " berhasil diproses.");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Aksi gagal."); }
    finally { setBusy(""); }
  }

  async function adjustStock(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!productId.trim() || !reason.trim()) { setError("Product ID dan alasan mutasi wajib diisi."); return; }
    setBusy("inventory"); setError(""); setNotice("");
    try {
      await api("/v1/admin/inventory/mutations", {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ action: movement, product_id: productId.trim(), payload: { quantity: Number(quantity), reason: reason.trim() } }),
      });
      setNotice("Mutasi stok tersimpan dan ledger diperbarui.");
      setProductId(""); setReason(""); await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Mutasi stok gagal."); }
    finally { setBusy(""); }
  }

  const tabs: { id: Tab; name: string; icon: typeof Boxes }[] = [
    { id: "inventory", name: "Inventori", icon: Boxes }, { id: "orders", name: "Pesanan", icon: Truck },
    { id: "payments", name: "Pembayaran", icon: CreditCard }, { id: "returns", name: "Retur & Refund", icon: RotateCcw },
  ];

  return <main className="min-h-screen bg-slate-50 text-slate-900">
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3"><Link href="/admin" className="rounded-lg border p-2" aria-label="Kembali"><ArrowLeft size={18}/></Link><div><p className="text-xs font-semibold uppercase tracking-wide text-orange-600">OtoClinic · Operasional</p><h1 className="text-xl font-bold sm:text-2xl">Inventory & Order Lifecycle</h1></div></div>
        <button onClick={() => void load()} className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold hover:bg-slate-50" disabled={loading}><RefreshCw size={16}/> Refresh</button>
      </div>
    </header>
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="Area transaksi">
        {tabs.map(t => { const Icon = t.icon; return <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} className={"inline-flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold " + (tab === t.id ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-100")}><Icon size={17}/>{t.name}</button>; })}
      </div>
      {error && <div role="alert" className="mb-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
      {notice && <div role="status" className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</div>}
      {loading ? <div className="rounded-xl border bg-white p-8 text-sm text-slate-500">Memuat data transaksi nyata dari API…</div> :
      <>
        {tab === "inventory" && <section className="space-y-5">
          {["admin", "inventory_manager"].includes(role) && <form onSubmit={adjustStock} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-5">
            <label className="text-sm font-medium">Product UUID<input required value={productId} onChange={e=>setProductId(e.target.value)} placeholder="UUID produk terbit" className="mt-1 w-full rounded-lg border p-2.5 font-normal"/></label>
            <label className="text-sm font-medium">Jenis mutasi<select value={movement} onChange={e=>setMovement(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5 font-normal"><option value="receipt">Penerimaan</option><option value="adjustment_increase">Penyesuaian +</option><option value="adjustment_decrease">Penyesuaian −</option><option value="write_off">Write-off</option></select></label>
            <label className="text-sm font-medium">Kuantitas<input required min="1" max="1000000" type="number" value={quantity} onChange={e=>setQuantity(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5 font-normal"/></label>
            <label className="text-sm font-medium">Alasan<input required value={reason} onChange={e=>setReason(e.target.value)} placeholder="Alasan dan bukti internal" className="mt-1 w-full rounded-lg border p-2.5 font-normal"/></label>
            <button disabled={busy==="inventory"} className="self-end rounded-lg bg-orange-600 px-4 py-2.5 font-semibold text-white disabled:opacity-50">Simpan mutasi</button>
          </form>}
          <div className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4"><h2 className="font-semibold">Saldo stok</h2><p className="text-sm text-slate-500">Stok tersedia = stok fisik − stok yang sedang direservasi.</p></div>
            {inventory.length===0 ? <p className="p-8 text-sm text-slate-500">Belum ada saldo stok terdaftar. Tidak ada stok contoh yang dibuat.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-slate-600"><tr><th className="p-3">Produk</th><th className="p-3">SKU</th><th className="p-3">Fisik</th><th className="p-3">Reservasi</th><th className="p-3">Tersedia</th><th className="p-3">Diperbarui</th></tr></thead><tbody>{inventory.map((r,i)=>{const p=r.products??{};return <tr key={r.product_id??i} className="border-t"><td className="p-3 font-medium">{p.name??"Produk"}</td><td className="p-3">{p.sku??"—"}</td><td className="p-3 tabular-nums">{r.on_hand}</td><td className="p-3 tabular-nums">{r.reserved}</td><td className="p-3 font-semibold tabular-nums">{Number(r.on_hand)-Number(r.reserved)}</td><td className="p-3 text-slate-500">{r.updated_at?new Date(r.updated_at).toLocaleString("id-ID"):"—"}</td></tr>})}</tbody></table></div>}
          </div>
        </section>}
        {tab === "orders" && <section className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4"><h2 className="font-semibold">Pesanan</h2><p className="text-sm text-slate-500">Stok dikonsumsi saat pengiriman dikonfirmasi; pembatalan sebelum diproses melepas reservasi.</p></div>
          {orders.length===0?<p className="p-8 text-sm text-slate-500">Belum ada pesanan.</p>:<div className="divide-y">{orders.map(o=><article key={o.id} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between"><div><p className="font-semibold">{o.id}</p><p className="text-sm text-slate-500">{new Date(o.created_at).toLocaleString("id-ID")} · {label[o.status]??o.status}</p><p className="mt-1 font-semibold">{money(o.total_amount)}</p>{o.tracking_code&&<p className="text-sm">Resi: {o.tracking_code}</p>}</div><div className="flex flex-wrap gap-2">
            {o.status==="payment_review"&&<span className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">Menunggu verifikasi pembayaran</span>}
            {o.status==="paid"&&<button onClick={()=>void mutate("/v1/admin/orders/"+o.id+"/mutations","start_fulfillment")} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Mulai proses</button>}
            {o.status==="processing"&&<button onClick={()=>{const tracking=window.prompt("Masukkan nomor resi pengiriman");if(tracking?.trim())void mutate("/v1/admin/orders/"+o.id+"/mutations","mark_shipped",{tracking_code:tracking.trim()})}} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Tandai dikirim</button>}
            {o.status==="shipped"&&<button onClick={()=>void mutate("/v1/admin/orders/"+o.id+"/mutations","mark_delivered")} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">Tandai diterima</button>}
            {["pending_payment","payment_review"].includes(o.status)&&<button onClick={()=>void mutate("/v1/admin/orders/"+o.id+"/mutations","cancel_order")} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700">Batalkan</button>}
          </div></article>)}</div>}
        </section>}
        {tab === "payments" && <section className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4"><h2 className="font-semibold">Verifikasi pembayaran</h2><p className="text-sm text-slate-500">Bukti transfer hanya bukti pengajuan. Verifikasi harus dilakukan personel berwenang.</p></div>
          {payments.length===0?<p className="p-8 text-sm text-slate-500">Tidak ada pembayaran menunggu review.</p>:<div className="divide-y">{payments.map(p=><article key={p.id} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between"><div><p className="font-semibold">Order {p.order_id}</p><p className="text-sm text-slate-500">Bukti: {p.evidence_reference??"—"} · {new Date(p.created_at).toLocaleString("id-ID")}</p><p className="font-semibold">{money(p.amount)}</p></div><div className="flex flex-wrap gap-2"><button onClick={()=>{const ref=window.prompt("Nomor referensi bank/provider atau catatan verifikasi wajib");if(ref?.trim())void mutate("/v1/admin/orders/"+p.order_id+"/mutations","verify_payment",{payment_event_id:p.id,provider_reference:ref.trim()})}} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">Verifikasi</button><button onClick={()=>{const reason=window.prompt("Alasan penolakan pembayaran");if(reason?.trim())void mutate("/v1/admin/orders/"+p.order_id+"/mutations","reject_payment",{payment_event_id:p.id,reason:reason.trim()})}} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700">Tolak</button></div></article>)}</div>}
        </section>}
        {tab === "returns" && <section className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4"><h2 className="font-semibold">Retur dan refund</h2><p className="text-sm text-slate-500">Barang yang diterima tidak otomatis ditambahkan ke stok. Pilih item yang sudah diperiksa dan layak dijual saat penerimaan retur.</p></div>
          {returns.length===0?<p className="p-8 text-sm text-slate-500">Tidak ada permintaan retur baru.</p>:<div className="divide-y">{returns.map(r=><article key={r.id} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between"><div><p className="font-semibold">Order {r.order_id}</p><p className="text-sm text-slate-500">{r.reason}</p><p className="font-semibold">{money(r.requested_refund)}</p></div><div className="flex flex-wrap gap-2"><button onClick={()=>void mutate("/v1/admin/orders/"+r.order_id+"/mutations","approve_return",{return_id:r.id})} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Setujui retur</button><button onClick={()=>{const reason=window.prompt("Alasan penolakan retur");if(reason?.trim())void mutate("/v1/admin/orders/"+r.order_id+"/mutations","reject_return",{return_id:r.id,reason:reason.trim()})}} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700">Tolak</button></div></article>)}</div>}
        </section>}
      </>}
      <p className="mt-6 text-xs text-slate-500">Transaksi berjalan melalui FastAPI dan RPC PostgreSQL ber-idempotensi. Provider pembayaran/logistik eksternal belum diaktifkan oleh Phase 07.</p>
    </div>
  </main>;
}
