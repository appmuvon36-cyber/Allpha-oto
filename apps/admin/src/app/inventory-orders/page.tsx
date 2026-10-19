"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Boxes, CreditCard, RefreshCw, RotateCcw, Truck } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
type Row = { [key: string]: JsonValue };
const asRow = (value: unknown): Row => typeof value === "object" && value !== null && !Array.isArray(value) ? value as Row : {};
const asText = (value: unknown, fallback = "—") => typeof value === "string" || typeof value === "number" ? String(value) : fallback;
type Tab = "inventory" | "orders" | "payments" | "returns";

const money = (value: unknown) => new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(Number(value ?? 0));
const handoffLabel: Record<string, string> = { not_started: "Belum diminta", prepared: "Menunggu tindak lanjut", confirmed: "Dikonfirmasi staf", declined: "Ditolak staf", expired: "Kedaluwarsa" };

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
    if (!response.ok) throw new Error(asText(body.detail, "Permintaan gagal (HTTP " + response.status + ")."));
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
    const canManageOrders = ["admin", "order_manager"].includes(profile.role ?? "");
    const paths = [
      fetch(API + "/v1/admin/inventory?limit=100", { headers, cache: "no-store" }),
      canManageOrders ? fetch(API + "/v1/admin/orders?limit=100", { headers, cache: "no-store" }) : Promise.resolve(null),
      canManageOrders ? fetch(API + "/v1/admin/payments?status=pending_review&limit=100", { headers, cache: "no-store" }) : Promise.resolve(null),
      canManageOrders ? Promise.all(["requested", "approved", "refund_pending"].map(status => fetch(API + "/v1/admin/returns?status=" + status + "&limit=100", { headers, cache: "no-store" }))) : Promise.resolve(null),
    ];
    const [inventoryResponse, orderResponse, paymentResponse, returnResponses] = await Promise.all(paths);
    const readResponse = async (r: Response | null) => r ? ({ ok: r.ok, status: r.status, body: await r.json().catch(() => ({})) }) : ({ ok: true, status: 200, body: { items: [] } });
    const inventoryBody = await readResponse(inventoryResponse as Response);
    const orderBody = await readResponse(orderResponse as Response | null);
    const paymentBody = await readResponse(paymentResponse as Response | null);
    const returnList = returnResponses ? await Promise.all((returnResponses as Response[]).map(readResponse)) : [];
    const bodies = [inventoryBody, orderBody, paymentBody, ...returnList];
    const failed = bodies.find(x => !x.ok);
    if (failed) { setError("Queue transaksi tidak dapat dimuat (HTTP " + failed.status + "). Pastikan API, role, dan kebijakan RLS tersedia."); setLoading(false); return; }
    setInventory(bodies[0].body.items ?? []);
    setOrders(bodies[1].body.items ?? []);
    setPayments(bodies[2].body.items ?? []);
    setReturns(returnList.flatMap(x => x.body.items ?? []));
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

  async function reviewWhatsAppHandoff(orderId: string, action: "confirm" | "decline") {
    let note: string | undefined;
    if (action === "decline") {
      const value = window.prompt("Alasan penolakan handoff WhatsApp (wajib):");
      if (!value?.trim()) return;
      note = value.trim();
    }
    if (!window.confirm(action === "confirm" ? "Konfirmasi bahwa tim menerima permintaan pesanan via WhatsApp?" : "Tolak permintaan handoff WhatsApp ini?")) return;
    setBusy("whatsapp-" + action); setError(""); setNotice("");
    try {
      const response = await api("/v1/admin/orders/" + orderId + "/whatsapp-handoff", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ action, note }),
      });
      const order = asRow(asRow(response.result).order);
      const status = asText(order.whatsapp_handoff_status, action === "confirm" ? "confirmed" : "declined");
      setNotice(status === "expired" ? "Handoff sudah kedaluwarsa; tidak dikonfirmasi." : action === "confirm" ? "Handoff WhatsApp dikonfirmasi staf." : "Handoff WhatsApp ditolak dan alasannya dicatat.");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Review handoff WhatsApp gagal."); }
    finally { setBusy(""); }
  }

  async function adjustStock(event: import("react").FormEvent<HTMLFormElement>) {
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

  async function expireReservations() {
    if (!window.confirm("Batalkan pesanan belum dibayar yang reservasinya sudah kedaluwarsa dan lepaskan stok yang dicadangkan?")) return;
    setBusy("expire-reservations"); setError(""); setNotice("");
    try {
      const result = await api("/v1/admin/inventory/expire-reservations", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() } });
      const data = asRow(result.result);
      setNotice(Number(data.cancelled_orders ?? 0) + " pesanan dibatalkan; " + Number(data.released_reservations ?? 0) + " reservasi stok dilepaskan.");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Pembersihan reservasi gagal."); }
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
          <div className="flex flex-col justify-between gap-3 rounded-xl border bg-white p-4 sm:flex-row sm:items-center"><div><p className="font-semibold">Reservasi kedaluwarsa</p><p className="text-xs text-slate-500">Batalkan pesanan belum dibayar yang melewati batas reservasi 30 menit.</p></div><button disabled={busy==="expire-reservations"} onClick={()=>void expireReservations()} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold disabled:opacity-50">Lepaskan reservasi kedaluwarsa</button></div>
          {["admin", "inventory_manager"].includes(role) && <form onSubmit={adjustStock} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-5">
            <label className="text-sm font-medium">Product UUID<input required value={productId} onChange={e=>setProductId(e.target.value)} placeholder="UUID produk terbit" className="mt-1 w-full rounded-lg border p-2.5 font-normal"/></label>
            <label className="text-sm font-medium">Jenis mutasi<select value={movement} onChange={e=>setMovement(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5 font-normal"><option value="receipt">Penerimaan</option><option value="adjustment_increase">Penyesuaian +</option><option value="adjustment_decrease">Penyesuaian −</option><option value="write_off">Write-off</option></select></label>
            <label className="text-sm font-medium">Kuantitas<input required min="1" max="1000000" type="number" value={quantity} onChange={e=>setQuantity(e.target.value)} className="mt-1 w-full rounded-lg border p-2.5 font-normal"/></label>
            <label className="text-sm font-medium">Alasan<input required value={reason} onChange={e=>setReason(e.target.value)} placeholder="Alasan dan bukti internal" className="mt-1 w-full rounded-lg border p-2.5 font-normal"/></label>
            <button disabled={busy==="inventory"} className="self-end rounded-lg bg-orange-600 px-4 py-2.5 font-semibold text-white disabled:opacity-50">Simpan mutasi</button>
          </form>}
          <div className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4"><h2 className="font-semibold">Saldo stok</h2><p className="text-sm text-slate-500">Stok tersedia = stok fisik − stok yang sedang direservasi.</p></div>
            {inventory.length===0 ? <p className="p-8 text-sm text-slate-500">Belum ada saldo stok terdaftar. Tidak ada stok contoh yang dibuat.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-slate-600"><tr><th className="p-3">Produk</th><th className="p-3">SKU</th><th className="p-3">Fisik</th><th className="p-3">Reservasi</th><th className="p-3">Tersedia</th><th className="p-3">Diperbarui</th></tr></thead><tbody>{inventory.map((r,i)=>{const p=asRow(r.products);return <tr key={asText(r.product_id,String(i))} className="border-t"><td className="p-3 font-medium">{asText(p.name,"Produk")}</td><td className="p-3">{asText(p.sku)}</td><td className="p-3 tabular-nums">{asText(r.on_hand,"0")}</td><td className="p-3 tabular-nums">{asText(r.reserved,"0")}</td><td className="p-3 font-semibold tabular-nums">{Number(r.on_hand??0)-Number(r.reserved??0)}</td><td className="p-3 text-slate-500">{r.updated_at?new Date(String(r.updated_at)).toLocaleString("id-ID"):"—"}</td></tr>})}</tbody></table></div>}
          </div>
        </section>}
        {tab === "orders" && <section className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4"><h2 className="font-semibold">Pesanan</h2><p className="text-sm text-slate-500">Stok dikonsumsi saat pengiriman dikonfirmasi; pembatalan sebelum diproses melepas reservasi.</p></div>
          {orders.length===0?<p className="p-8 text-sm text-slate-500">Belum ada pesanan.</p>:<div className="divide-y">{orders.map(o=><article key={asText(o.id)} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between"><div><p className="font-semibold">{asText(o.id)}</p><p className="text-sm text-slate-500">{new Date(String(o.created_at)).toLocaleString("id-ID")} · {label[asText(o.status,"")]??asText(o.status)}</p><p className="mt-1 font-semibold">{money(o.total_amount)}</p><p className="mt-1 text-xs text-slate-600">Kanal: {asText(o.sales_channel,"web")==="whatsapp"?"WhatsApp":"Web"} · Handoff: {asText(o.whatsapp_handoff_status,"not_started")==="prepared"&&typeof o.whatsapp_handoff_expires_at==="string"&&Date.parse(o.whatsapp_handoff_expires_at)<=Date.now()?"Kedaluwarsa":handoffLabel[asText(o.whatsapp_handoff_status,"not_started")]??asText(o.whatsapp_handoff_status)}</p>{o.whatsapp_handoff_expires_at&&<p className="text-xs text-slate-500">Batas handoff: {new Date(String(o.whatsapp_handoff_expires_at)).toLocaleString("id-ID")}</p>}{o.whatsapp_handoff_review_note&&<p className="text-xs text-slate-500">Catatan staf: {asText(o.whatsapp_handoff_review_note)}</p>}{o.tracking_code&&<p className="text-sm">Resi: {asText(o.tracking_code)}</p>}</div><div className="flex flex-wrap gap-2">
            {o.status==="payment_review"&&<span className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">Menunggu verifikasi pembayaran</span>}
            {o.status==="paid"&&<button onClick={()=>void mutate("/v1/admin/orders/"+asText(o.id)+"/mutations","start_fulfillment")} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Mulai proses</button>}
            {o.status==="processing"&&<button onClick={()=>{const tracking=window.prompt("Masukkan nomor resi pengiriman");if(tracking?.trim())void mutate("/v1/admin/orders/"+asText(o.id)+"/mutations","mark_shipped",{tracking_code:tracking.trim()})}} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Tandai dikirim</button>}
            {o.status==="shipped"&&<button onClick={()=>void mutate("/v1/admin/orders/"+asText(o.id)+"/mutations","mark_delivered")} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">Tandai diterima</button>}
            {asText(o.whatsapp_handoff_status,"not_started")==="prepared"&&!(typeof o.whatsapp_handoff_expires_at==="string"&&Date.parse(o.whatsapp_handoff_expires_at)<=Date.now())&&<><button disabled={busy.startsWith("whatsapp-")} onClick={()=>void reviewWhatsAppHandoff(asText(o.id),"confirm")} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Konfirmasi handoff</button><button disabled={busy.startsWith("whatsapp-")} onClick={()=>void reviewWhatsAppHandoff(asText(o.id),"decline")} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700 disabled:opacity-50">Tolak handoff</button></>}
            {["pending_payment","payment_review"].includes(asText(o.status,""))&&<button onClick={()=>void mutate("/v1/admin/orders/"+asText(o.id)+"/mutations","cancel_order")} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700">Batalkan</button>}
          </div></article>)}</div>}
        </section>}
        {tab === "payments" && <section className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4"><h2 className="font-semibold">Verifikasi pembayaran</h2><p className="text-sm text-slate-500">Bukti transfer hanya bukti pengajuan. Verifikasi harus dilakukan personel berwenang.</p></div>
          {payments.length===0?<p className="p-8 text-sm text-slate-500">Tidak ada pembayaran menunggu review.</p>:<div className="divide-y">{payments.map(p=><article key={asText(p.id)} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between"><div><p className="font-semibold">Order {asText(p.order_id)}</p><p className="text-sm text-slate-500">Bukti: {asText(p.evidence_reference)} · {new Date(String(p.created_at)).toLocaleString("id-ID")}</p><p className="font-semibold">{money(p.amount)}</p></div><div className="flex flex-wrap gap-2"><button onClick={()=>{const ref=window.prompt("Nomor referensi bank/provider atau catatan verifikasi wajib");if(ref?.trim())void mutate("/v1/admin/orders/"+asText(p.order_id)+"/mutations","verify_payment",{payment_event_id:p.id,provider_reference:ref.trim()})}} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">Verifikasi</button><button onClick={()=>{const reason=window.prompt("Alasan penolakan pembayaran");if(reason?.trim())void mutate("/v1/admin/orders/"+asText(p.order_id)+"/mutations","reject_payment",{payment_event_id:p.id,reason:reason.trim()})}} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700">Tolak</button></div></article>)}</div>}
        </section>}
        {tab === "returns" && <section className="overflow-hidden rounded-2xl border bg-white"><div className="border-b p-4"><h2 className="font-semibold">Retur dan refund</h2><p className="text-sm text-slate-500">Barang yang diterima tidak otomatis ditambahkan ke stok. Pilih item yang sudah diperiksa dan layak dijual saat penerimaan retur.</p></div>
          {returns.length===0?<p className="p-8 text-sm text-slate-500">Tidak ada permintaan retur baru.</p>:<div className="divide-y">{returns.map(r=><article key={asText(r.id)} className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between"><div><p className="font-semibold">Order {asText(r.order_id)}</p><p className="text-sm text-slate-500">{asText(r.reason)}</p><p className="font-semibold">{money(r.requested_refund)}</p></div><div className="flex flex-wrap gap-2">{r.status==="requested"&&<><button onClick={()=>void mutate("/v1/admin/orders/"+asText(r.order_id)+"/mutations","approve_return",{return_id:r.id})} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Setujui retur</button><button onClick={()=>{const reason=window.prompt("Alasan penolakan retur");if(reason?.trim())void mutate("/v1/admin/orders/"+asText(r.order_id)+"/mutations","reject_return",{return_id:r.id,reason:reason.trim()})}} className="rounded-lg border border-red-200 px-3 py-2 text-sm font-semibold text-red-700">Tolak</button></>}{r.status==="approved"&&<button onClick={async()=>{try{const detail=await api("/v1/orders/"+asText(r.order_id));const options=(detail.items??[]).map((item:Row)=>asText(item.name_snapshot)+" · "+asText(item.id)).join("\n");const selected=window.prompt("Barang sudah diterima fisik. Masukkan UUID item yang lolos inspeksi untuk restock, pisahkan koma. Kosong = tidak restock.\n"+options,"");if(selected===null)return;const restock_items=selected.split(",").map(x=>x.trim()).filter(Boolean);await mutate("/v1/admin/orders/"+asText(r.order_id)+"/mutations","receive_return",{return_id:r.id,restock_items});}catch(e){setError(e instanceof Error?e.message:"Detail retur tidak dapat dimuat.");}}} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">Terima & inspeksi</button>}{r.status==="refund_pending"&&<button onClick={()=>{const ref=window.prompt("Referensi refund dari provider yang sudah dieksekusi");if(ref?.trim())void mutate("/v1/admin/orders/"+asText(r.order_id)+"/mutations","record_refund",{return_id:r.id,provider_reference:ref.trim()})}} className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white">Catat refund</button>}</div></article>)}</div>}
        </section>}
      </>}
      <p className="mt-6 text-xs text-slate-500">Transaksi berjalan melalui FastAPI dan RPC PostgreSQL ber-idempotensi. Provider pembayaran/logistik eksternal belum diaktifkan oleh Phase 07.</p>
    </div>
  </main>;
}
