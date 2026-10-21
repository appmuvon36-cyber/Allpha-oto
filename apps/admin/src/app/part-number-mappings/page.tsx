"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, ExternalLink, RefreshCw, ShieldCheck, X } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
type Mapping = {
  id: string; canonical_part_number: string; alternate_part_number: string;
  canonical_type: "oem" | "aftermarket"; alternate_type: "oem" | "aftermarket";
  relation_type: string; manufacturer: string | null; source_type: string; source_name: string;
  source_url: string; source_reference: string | null; source_checked_at: string;
  review_status: "pending_review" | "approved" | "rejected"; review_note: string | null;
  reviewed_at: string | null; created_at: string;
};
const sourceLabels: Record<string,string> = {
  manufacturer_catalog: "Katalog pabrikan", oem_catalog: "Katalog OEM",
  authorized_distributor_catalog: "Distributor resmi", tecdoc: "TecDoc",
  verified_supplier_catalog: "Katalog pemasok terverifikasi",
};
const statusLabels: Record<string,string> = { pending_review:"Menunggu review", approved:"Disetujui", rejected:"Ditolak" };

export default function PartNumberMappingsPage() {
  const router = useRouter();
  const supabase = getSupabaseBrowserClient();
  const [token,setToken] = useState("");
  const [role,setRole] = useState("");
  const [items,setItems] = useState<Mapping[]>([]);
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [form,setForm] = useState({
    canonical_part_number:"", alternate_part_number:"", canonical_type:"oem", alternate_type:"aftermarket",
    relation_type:"cross_reference", manufacturer:"", source_type:"manufacturer_catalog", source_name:"",
    source_url:"", source_reference:"", review_note:"",
  });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    if (!supabase) { setError("Supabase belum dikonfigurasi."); setLoading(false); return; }
    const {data:{session},error:authError} = await supabase.auth.getSession();
    if (authError || !session) { router.replace("/login"); setLoading(false); return; }
    setToken(session.access_token);
    const {data:profile,error:profileError} = await supabase.from("user_profiles").select("role,is_active").eq("id",session.user.id).maybeSingle();
    if (profileError || !profile?.is_active || !["admin","catalog_editor","moderator"].includes(profile.role ?? "")) {
      setError("Halaman ini membutuhkan akun aktif dengan role admin, catalog_editor, atau moderator."); setLoading(false); return;
    }
    setRole(profile.role);
    try {
      const response = await fetch(API+"/v1/admin/part-number-mappings?limit=100",{headers:{Authorization:"Bearer "+session.access_token}});
      const body = await response.json().catch(()=>({}));
      if (!response.ok) throw new Error(typeof body.detail==="string"?body.detail:"Pemetaan nomor part tidak dapat dimuat.");
      setItems((body.items ?? []) as Mapping[]);
    } catch (e) { setError(e instanceof Error ? e.message : "Pemetaan tidak dapat dimuat."); }
    finally { setLoading(false); }
  },[router,supabase]);

  useEffect(()=>{ void load(); },[load]);

  async function createMapping(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(API+"/v1/admin/part-number-mappings",{
        method:"POST", headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},
        body:JSON.stringify({
          ...form,
          manufacturer:form.manufacturer.trim()||undefined,
          source_reference:form.source_reference.trim()||undefined,
          review_note:form.review_note.trim()||undefined,
        }),
      });
      const body = await response.json().catch(()=>({}));
      if (!response.ok) throw new Error(typeof body.detail==="string"?body.detail:"Pemetaan tidak dapat disimpan.");
      setNotice("Pemetaan disimpan sebagai menunggu review. Belum digunakan dalam pencarian publik.");
      setForm(v=>({...v,canonical_part_number:"",alternate_part_number:"",manufacturer:"",source_name:"",source_url:"",source_reference:"",review_note:""}));
      await load();
    } catch(e) { setError(e instanceof Error?e.message:"Pemetaan tidak dapat disimpan."); }
    finally { setBusy(false); }
  }

  async function reviewMapping(item: Mapping, action: "approve"|"reject") {
    const label = action==="approve"?"menyetujui":"menolak";
    if (!window.confirm("Konfirmasi "+label+" cross-reference "+item.canonical_part_number+" ↔ "+item.alternate_part_number+"? Ini tidak mengubah status fitment produk.")) return;
    setBusy(true);setError("");setNotice("");
    try {
      const response=await fetch(API+"/v1/admin/part-number-mappings/"+encodeURIComponent(item.id)+"/review",{
        method:"PATCH",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},
        body:JSON.stringify({action,review_note:item.review_note??""}),
      });
      const body=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(typeof body.detail==="string"?body.detail:"Review pemetaan gagal.");
      setNotice("Review tersimpan. Status fitment produk tidak berubah.");
      await load();
    }catch(e){setError(e instanceof Error?e.message:"Review pemetaan gagal.");}
    finally{setBusy(false);}
  }

  return <main className="min-h-screen bg-[var(--color-canvas)] text-slate-900">
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link href="/admin" className="inline-flex min-h-10 items-center gap-2 text-sm font-bold text-slate-600"><ArrowLeft size={17}/> Dashboard</Link>
        <button onClick={()=>void load()} disabled={loading||busy} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-bold disabled:opacity-50"><RefreshCw size={15}/> Muat ulang</button>
      </div>
    </header>
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
      <div>
        <p className="text-xs font-extrabold uppercase tracking-[.16em] text-[var(--color-primary)]">Phase 10 · Search intelligence</p>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight">Cross-reference nomor part</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Catat relasi nomor OEM dan aftermarket dengan sumber tepercaya. Semua entri baru berstatus menunggu review; hanya pemetaan yang disetujui yang dapat memengaruhi pencarian publik. Ini bukan bukti fitment kendaraan.</p>
        {role && <p className="mt-2 text-xs text-slate-500">Role aktif: {role}</p>}
      </div>
      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>}
      {notice && <div role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</div>}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-bold">Tambah pemetaan dengan bukti sumber</h2>
        <p className="mt-1 text-sm text-slate-500">Masukkan sumber yang benar-benar telah diperiksa. Jangan mengisi nomor berdasarkan tebakan atau kemiripan teks.</p>
        <form onSubmit={createMapping} className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="grid gap-1.5 text-sm font-semibold">Nomor OEM
            <input required maxLength={120} value={form.canonical_part_number} onChange={e=>setForm(v=>({...v,canonical_part_number:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 px-3 font-normal" placeholder="Nomor sesuai katalog OEM"/>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold">Nomor aftermarket
            <input required maxLength={120} value={form.alternate_part_number} onChange={e=>setForm(v=>({...v,alternate_part_number:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 px-3 font-normal" placeholder="Nomor produk aftermarket"/>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold">Relasi
            <select value={form.relation_type} onChange={e=>setForm(v=>({...v,relation_type:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 font-normal">
              <option value="cross_reference">Cross-reference</option><option value="supersedes">Nomor pengganti terbaru</option><option value="replaces">Menggantikan nomor lama</option>
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold">Pabrikan / merek
            <input maxLength={180} value={form.manufacturer} onChange={e=>setForm(v=>({...v,manufacturer:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 px-3 font-normal" placeholder="Opsional"/>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold">Jenis sumber tepercaya
            <select value={form.source_type} onChange={e=>setForm(v=>({...v,source_type:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 font-normal">
              {Object.entries(sourceLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold">Nama sumber
            <input required minLength={2} maxLength={180} value={form.source_name} onChange={e=>setForm(v=>({...v,source_name:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 px-3 font-normal" placeholder="Nama katalog / distributor"/>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold sm:col-span-2 lg:col-span-3">URL bukti sumber
            <input required type="url" maxLength={1000} value={form.source_url} onChange={e=>setForm(v=>({...v,source_url:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 px-3 font-normal" placeholder="https://..."/>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold">Referensi dokumen / halaman
            <input maxLength={300} value={form.source_reference} onChange={e=>setForm(v=>({...v,source_reference:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 px-3 font-normal" placeholder="Opsional"/>
          </label>
          <label className="grid gap-1.5 text-sm font-semibold sm:col-span-2">Catatan review
            <input maxLength={1000} value={form.review_note} onChange={e=>setForm(v=>({...v,review_note:e.target.value}))} className="min-h-11 rounded-xl border border-slate-300 px-3 font-normal" placeholder="Catatan pemeriksaan sumber"/>
          </label>
          <div className="flex items-end"><button disabled={busy||loading||!token} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-5 text-sm font-bold text-white disabled:opacity-50"><ShieldCheck size={16}/>{busy?"Menyimpan…":"Simpan untuk review"}</button></div>
        </form>
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-5"><div><h2 className="text-lg font-bold">Daftar pemetaan</h2><p className="mt-1 text-sm text-slate-500">Data dari database produksi; tidak ada baris contoh.</p></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold">{items.length} entri</span></div>
        {loading ? <p className="p-6 text-sm text-slate-500">Memuat pemetaan…</p> : items.length===0 ? <div className="p-8 text-center"><p className="font-semibold">Belum ada pemetaan nomor part.</p><p className="mt-1 text-sm text-slate-500">Tambahkan hanya relasi yang didukung sumber tepercaya dan review manual.</p></div> : <div className="divide-y divide-slate-100">
          {items.map(item=><article key={item.id} className="grid gap-4 p-5 lg:grid-cols-[1fr_1fr_auto]">
            <div><div className="flex flex-wrap items-center gap-2"><span className="font-bold">{item.canonical_part_number}</span><span className="text-slate-400">↔</span><span className="font-bold">{item.alternate_part_number}</span><span className={"rounded-full px-2.5 py-1 text-xs font-bold "+(item.review_status==="approved"?"bg-emerald-50 text-emerald-800":item.review_status==="rejected"?"bg-red-50 text-red-800":"bg-amber-50 text-amber-800")}>{statusLabels[item.review_status]??item.review_status}</span></div><p className="mt-2 text-xs text-slate-500">{item.canonical_type.toUpperCase()} → {item.alternate_type.toUpperCase()} · {item.relation_type}{item.manufacturer?" · "+item.manufacturer:""}</p></div>
            <div className="text-sm"><p className="font-semibold">{sourceLabels[item.source_type]??item.source_type}: {item.source_name}</p><a href={item.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 break-all text-blue-700 underline"><ExternalLink size={13}/> Buka bukti sumber</a>{item.source_reference&&<p className="mt-1 text-xs text-slate-500">Referensi: {item.source_reference}</p>}{item.review_note&&<p className="mt-1 text-xs text-slate-500">Catatan: {item.review_note}</p>}</div>
            <div className="flex flex-wrap items-start gap-2">{item.review_status==="pending_review"&&<><button disabled={busy} onClick={()=>void reviewMapping(item,"approve")} className="inline-flex min-h-10 items-center gap-1.5 rounded-xl bg-emerald-700 px-3 text-xs font-bold text-white disabled:opacity-50"><Check size={14}/> Setujui</button><button disabled={busy} onClick={()=>void reviewMapping(item,"reject")} className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-red-200 px-3 text-xs font-bold text-red-700 disabled:opacity-50"><X size={14}/> Tolak</button></>}</div>
          </article>)}
        </div>}
      </section>
      <p className="text-xs leading-5 text-slate-500">Peringatan: cross-reference nomor part adalah petunjuk pencarian berbasis sumber, bukan jaminan kecocokan kendaraan. Status fitment tetap harus diverifikasi melalui alur fitment yang terpisah.</p>
    </div>
  </main>;
}
