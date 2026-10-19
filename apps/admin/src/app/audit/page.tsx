"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Activity, ArrowLeft, ChevronLeft, ChevronRight, Filter, RefreshCw, Search } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
type AuditEvent = { id: string; actor_user_id: string | null; action: string; entity_type: string; entity_id: string | null; request_id: string | null; created_at: string };
type AuditResponse = { items: AuditEvent[]; count: number; limit: number; offset: number; next_offset: number | null };
type AuditFilters = { q?: string; action?: string; entity_type?: string };

const actionLabels: Record<string, string> = {
  create_product: "Membuat produk", update_product: "Memperbarui produk", submit_review: "Mengajukan review",
  approve_product: "Menyetujui produk", publish_product: "Mempublikasikan produk", reject_product: "Menolak produk",
  archive_product: "Mengarsipkan produk", approve_supplier: "Menyetujui pemasok", reject_supplier: "Menolak pemasok",
  suspend_supplier: "Menangguhkan pemasok", review_supplier_document: "Review dokumen pemasok",
  approve_offer: "Menyetujui penawaran", reject_offer: "Menolak penawaran", match_offer_product: "Menghubungkan penawaran",
  oto_inventory_mutate: "Mutasi inventori", inventory_mutation: "Mutasi inventori",
  oto_order_mutate: "Mutasi pesanan", verify_payment: "Verifikasi pembayaran",
  admin_set_user_role: "Perubahan role pengguna", expire_reservations: "Melepas reservasi kedaluwarsa",
};

export default function AdminAuditPage() {
  const router = useRouter();
  const supabase = getSupabaseBrowserClient();
  const [data, setData] = useState<AuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [filters, setFilters] = useState<AuditFilters>({});
  const [offset, setOffset] = useState(0);

  const load = useCallback(async (requestedOffset = 0, activeFilters: AuditFilters = {}) => {
    setLoading(true); setError("");
    if (!supabase) { setError("Autentikasi Supabase belum dikonfigurasi."); setLoading(false); return; }
    try {
      const { data: { session }, error: authError } = await supabase.auth.getSession();
      if (authError) throw new Error("Sesi tidak dapat diperiksa.");
      if (!session?.access_token) { router.replace("/login"); return; }
      const params = new URLSearchParams({ limit: "50", offset: String(requestedOffset) });
      if (activeFilters.q) params.set("q", activeFilters.q);
      if (activeFilters.action) params.set("action", activeFilters.action);
      if (activeFilters.entity_type) params.set("entity_type", activeFilters.entity_type);
      const response = await fetch(API + "/v1/admin/audit?" + params.toString(), {
        headers: { Authorization: "Bearer " + session.access_token, Accept: "application/json" }, cache: "no-store",
      });
      if (response.status === 401) { router.replace("/login"); return; }
      if (response.status === 403) throw new Error("Akses ditolak. Audit explorer hanya tersedia untuk administrator aktif.");
      if (!response.ok) throw new Error("Audit log tidak dapat dimuat (HTTP " + response.status + ").");
      setData(await response.json() as AuditResponse);
      setOffset(requestedOffset);
      setFilters(activeFilters);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Audit log tidak dapat dimuat.");
    } finally { setLoading(false); }
  }, [router, supabase]);

  useEffect(() => { void load(0, {}); }, [load]);

  function submitFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void load(0, { q: q.trim(), action: action.trim(), entity_type: entityType.trim() });
  }

  return <main className="min-h-screen bg-[var(--color-canvas)]">
    <header className="border-b border-[var(--color-border)] bg-white"><div className="mx-auto flex min-h-[68px] max-w-7xl items-center justify-between px-4 sm:px-6"><Link href="/admin" className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 hover:text-slate-900"><ArrowLeft size={16}/> Dashboard</Link><span className="inline-flex items-center gap-2 text-xs font-bold text-slate-500"><Activity size={15}/> Admin-only</span></div></header>
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-extrabold uppercase tracking-[.18em] text-[var(--color-primary)]">Governance</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight">Audit explorer</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Riwayat tindakan administratif yang tersimpan di database. Tampilan hanya memuat metadata aman; payload sensitif tidak diekspos.</p></div><button onClick={() => void load(offset, filters)} disabled={loading} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold disabled:opacity-50"><RefreshCw size={15}/> Muat ulang</button></div>
      <form onSubmit={submitFilters} className="mt-6 grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-[1.5fr_1fr_1fr_auto] sm:p-5">
        <label className="block text-xs font-bold text-slate-600">Pencarian<input value={q} onChange={e => setQ(e.target.value)} maxLength={80} placeholder="Aksi, jenis entitas, request ID" className="mt-2 min-h-11 w-full rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-[var(--color-primary)]"/></label>
        <label className="block text-xs font-bold text-slate-600">Aksi<input value={action} onChange={e => setAction(e.target.value)} maxLength={80} placeholder="Mis. admin_set_user_role" className="mt-2 min-h-11 w-full rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-[var(--color-primary)]"/></label>
        <label className="block text-xs font-bold text-slate-600">Jenis entitas<input value={entityType} onChange={e => setEntityType(e.target.value)} maxLength={80} placeholder="Mis. user_profile" className="mt-2 min-h-11 w-full rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-[var(--color-primary)]"/></label>
        <div className="flex items-end gap-2"><button className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 text-sm font-bold text-white"><Search size={15}/> Filter</button><button type="button" onClick={() => { setQ(""); setAction(""); setEntityType(""); void load(0, {}); }} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-semibold"><Filter size={15}/> Reset</button></div>
      </form>
      {error && <p role="alert" className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
      <section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 p-5"><div><h2 className="font-extrabold">Peristiwa audit</h2><p className="mt-1 text-xs text-slate-500">Paling baru lebih dahulu · maksimal 50 per halaman</p></div><span className="text-xs text-slate-500">{data ? data.items.length + " baris" : "—"}</span></div>
        {loading ? <div className="p-8 text-sm text-slate-500">Memuat audit melalui API…</div>
        : !data || data.items.length === 0 ? <div className="p-10 text-center"><Activity size={30} className="mx-auto text-slate-300"/><h3 className="mt-3 font-bold">Tidak ada peristiwa yang cocok</h3><p className="mt-1 text-sm text-slate-500">Jika database belum memiliki aktivitas, daftar akan tetap kosong. Tidak ada audit contoh yang dibuat.</p></div>
        : <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500"><tr>{["Waktu","Aksi","Entitas","ID entitas","Aktor","Request ID"].map(label => <th key={label} className="px-4 py-3 font-bold">{label}</th>)}</tr></thead><tbody>{data.items.map(item => <tr key={item.id} className="border-t border-slate-100 align-top text-xs"><td className="whitespace-nowrap px-4 py-4 text-slate-500">{new Date(item.created_at).toLocaleString("id-ID")}</td><td className="px-4 py-4"><span className="font-bold">{actionLabels[item.action] ?? item.action}</span><span className="mt-1 block font-mono text-[10px] text-slate-400">{item.action}</span></td><td className="px-4 py-4">{item.entity_type}</td><td className="px-4 py-4 font-mono">{item.entity_id ?? "—"}</td><td className="px-4 py-4 font-mono">{item.actor_user_id ?? "system"}</td><td className="px-4 py-4 font-mono">{item.request_id ?? "—"}</td></tr>)}</tbody></table></div>}
        <div className="flex items-center justify-between border-t border-slate-100 p-4"><span className="text-xs text-slate-500">Offset {offset}</span><div className="flex gap-2"><button disabled={loading || offset === 0} onClick={() => void load(Math.max(0, offset - 50), filters)} className="inline-flex min-h-10 items-center gap-1 rounded-lg border border-slate-200 px-3 text-sm font-semibold disabled:opacity-40"><ChevronLeft size={15}/> Sebelumnya</button><button disabled={loading || data?.next_offset == null} onClick={() => data?.next_offset != null && void load(data.next_offset, filters)} className="inline-flex min-h-10 items-center gap-1 rounded-lg border border-slate-200 px-3 text-sm font-semibold disabled:opacity-40">Berikutnya <ChevronRight size={15}/></button></div></div>
      </section>
    </div>
  </main>;
}
