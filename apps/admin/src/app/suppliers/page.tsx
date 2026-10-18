"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Check, ExternalLink, RefreshCw, Truck, X } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type Supplier = { id:string; owner_user_id:string; legal_name:string; display_name:string; supplier_type:string; status:string; contact_name:string|null; contact_email:string|null; contact_phone:string|null; business_registration_number:string|null; website_url:string|null; created_at:string; review_note:string|null };
type Offer = { id:string; supplier_id:string; product_id:string|null; supplier_sku:string|null; source_url:string|null; source_evidence:Record<string,unknown>; condition:string; unit_cost:number|null; asking_price:number|null; stock_quantity:number; stock_checked_at:string|null; quote_expires_at:string|null; status:string; lead_time_days:number; minimum_order_quantity:number; warranty_days:number; source_verified_at:string|null; suppliers?:{display_name:string;legal_name:string;status:string}|null };
type AuditEvent = { id:string; actor_user_id:string; action:string; entity_type:string; entity_id:string|null; request_id:string|null; created_at:string };
type Candidate = { product_id:string; sku:string|null; part_number:string|null; name:string; brand:string|null; condition:string; status:string; match_reason:string; match_score:number; automatic_linking:boolean; fitment_verified:boolean };
type SupplierDocument = { id:string; supplier_id:string; document_type:string; storage_path:string; original_filename:string; content_type:string; file_size_bytes:number; sha256:string|null; expires_at:string|null; status:string; review_note:string|null; created_at:string; suppliers?:{display_name:string;legal_name:string;status:string}|null };

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
const statusLabel:Record<string,string>={pending_review:"Menunggu review",active:"Aktif",suspended:"Ditangguhkan",rejected:"Ditolak",unavailable:"Tidak tersedia",expired:"Kedaluwarsa",verified:"Terverifikasi"};

export default function SuppliersPage() {
  const router=useRouter();
  const supabase=getSupabaseBrowserClient();
  const [token,setToken]=useState("");
  const [role,setRole]=useState("");
  const [suppliers,setSuppliers]=useState<Supplier[]>([]);
  const [offers,setOffers]=useState<Offer[]>([]);
  const [documents,setDocuments]=useState<SupplierDocument[]>([]);
  const [auditEvents,setAuditEvents]=useState<AuditEvent[]>([]);
  const [candidateResults,setCandidateResults]=useState<Record<string,Candidate[]>>({});
  const [candidateBusy,setCandidateBusy]=useState("");
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [reason,setReason]=useState("");

  const load=useCallback(async()=>{
    setLoading(true);setError("");
    if(!supabase){setError("Supabase belum dikonfigurasi pada environment Admin.");setLoading(false);return;}
    const {data:{session},error:authError}=await supabase.auth.getSession();
    if(authError||!session){router.replace("/login");setLoading(false);return;}
    setToken(session.access_token);
    const {data:profile,error:profileError}=await supabase.from("user_profiles").select("role,is_active").eq("id",session.user.id).maybeSingle();
    if(profileError||!profile?.is_active||!["admin","moderator","catalog_editor","inventory_manager"].includes(profile.role??"")){
      setError("Akses Supplier & Sourcing memerlukan akun operasional aktif.");setLoading(false);return;
    }
    setRole(profile.role);
    const headers={Authorization:"Bearer "+session.access_token};
    const canReadDocs=["admin","moderator","catalog_editor"].includes(profile.role??"");
    const canReadAudit=profile.role==="admin";
    const [supplierResponse,offerResponse,documentResponse,auditResponse]=await Promise.all([
      fetch(API+"/v1/admin/suppliers",{headers,cache:"no-store"}),
      fetch(API+"/v1/admin/supplier-offers",{headers,cache:"no-store"}),
      canReadDocs?fetch(API+"/v1/admin/supplier-documents?status=pending_review",{headers,cache:"no-store"}):Promise.resolve(null),
      canReadAudit?fetch(API+"/v1/admin/supplier-audit?limit=50&offset=0",{headers,cache:"no-store"}):Promise.resolve(null),
    ]);
    const readResponse=async(r:Response|null)=>r?({ok:r.ok,status:r.status,body:await r.json().catch(()=>({}))}):({ok:true,status:200,body:{items:[]}});
    const bodies=await Promise.all([supplierResponse,offerResponse,documentResponse,auditResponse].map(readResponse));
    const failed=bodies.find(x=>!x.ok);
    if(failed){setError("Data supplier tidak dapat dimuat (HTTP "+failed.status+"). Periksa role, API, dan kebijakan database.");setLoading(false);return;}
    setSuppliers((bodies[0].body.items??[]) as Supplier[]);
    setOffers((bodies[1].body.items??[]) as Offer[]);
    setDocuments(canReadDocs?((bodies[2].body.items??[]) as SupplierDocument[]):[]);
    setAuditEvents(canReadAudit?((bodies[3].body.items??[]) as AuditEvent[]):[]);
    setLoading(false);
  },[supabase,router]);

  useEffect(()=>{void load();},[load]);

  async function mutate(action:string,target:{supplier_id?:string;offer_id?:string;document_id?:string},payload:Record<string,unknown>={}) {
    if(!token)return;
    const prompts:Record<string,string>={
      approve_supplier:"Setujui pemasok ini? Status akan menjadi aktif hanya jika dokumen valid sudah diverifikasi.",
      reject_supplier:"Tolak pendaftaran pemasok ini? Alasan penolakan akan dicatat ke audit.",
      suspend_supplier:"Tangguhkan pemasok aktif ini? Penawaran baru tidak dapat dikirim sampai status ditinjau kembali.",
      review_supplier_document:payload.status==="verified"?"Verifikasi dokumen ini setelah memeriksa isinya?":"Tolak dokumen pemasok ini? Alasan penolakan akan dicatat ke audit.",
      approve_offer:"Setujui penawaran ini? Pastikan bukti sumber, timestamp stok, dan quotation masih berlaku.",
      reject_offer:"Tolak penawaran pemasok ini? Alasan penolakan akan dicatat ke audit.",
      expire_offer:"Tandai penawaran ini kedaluwarsa sehingga tidak dipakai sebagai penawaran aktif?",
      match_offer_product:"Tautkan penawaran ke kandidat katalog ini? Tautan manual akan tetap berstatus pending review dan tidak mengonfirmasi fitment.",
    };
    if(!window.confirm(prompts[action]??"Lanjutkan aksi supplier ini?"))return;
    setBusy(action+Object.values(target).join(""));setError("");setNotice("");
    try{
      const response=await fetch(API+"/v1/admin/supplier-mutations",{
        method:"POST",
        headers:{"Content-Type":"application/json",Authorization:"Bearer "+token,"Idempotency-Key":crypto.randomUUID()},
        body:JSON.stringify({action,...target,payload}),
      });
      const body=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(body.detail??"Aksi supplier ditolak.");
      setNotice("Aksi "+action+" berhasil diproses dan dicatat dalam audit.");
      await load();
    }catch(e){setError(e instanceof Error?e.message:"Operasi supplier gagal.");}
    finally{setBusy("");}
  }

  async function findCandidates(offerId:string){
    if(!token)return;
    setCandidateBusy(offerId);setError("");
    try{
      const response=await fetch(API+"/v1/admin/supplier-offers/"+offerId+"/candidates",{headers:{Authorization:"Bearer "+token},cache:"no-store"});
      const body=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(body.detail??"Pencocokan kandidat gagal.");
      setCandidateResults((current)=>({...current,[offerId]:(body.result?.candidates??[]) as Candidate[]}));
    }catch(e){setError(e instanceof Error?e.message:"Pencocokan kandidat gagal.");}
    finally{setCandidateBusy("");}
  }

  async function openDocument(doc:SupplierDocument){
    if(!supabase)return;
    const {data,error:storageError}=await supabase.storage.from("supplier-verification-documents").createSignedUrl(doc.storage_path,120);
    if(storageError||!data?.signedUrl){setError("Dokumen tidak dapat dibuka. Periksa hak akses Storage.");return;}
    window.open(data.signedUrl,"_blank","noopener,noreferrer");
  }

  const canReview=role==="admin"||role==="moderator";
  const canReadDocuments=canReview||role==="catalog_editor";
  const canReadAudit=role==="admin";
  const money=(value:number|null)=>value===null?"—":new Intl.NumberFormat("id-ID",{style:"currency",currency:"IDR",maximumFractionDigits:0}).format(value);
  const date=(value:string|null)=>value?new Date(value).toLocaleString("id-ID",{dateStyle:"medium",timeStyle:"short"}):"Belum tercatat";

  return <main className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-text)]">
    <header className="border-b border-[var(--color-border)] bg-white"><div className="mx-auto flex min-h-[68px] max-w-7xl items-center justify-between gap-4 px-4 sm:px-6"><Link href="/admin" className="inline-flex items-center gap-2 text-sm font-bold"><ArrowLeft size={17}/> Workspace Admin</Link><button onClick={()=>void load()} disabled={loading} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-semibold disabled:opacity-50"><RefreshCw size={15}/> Muat ulang</button></div></header>
    <div className="mx-auto max-w-7xl px-4 py-7 sm:px-6 sm:py-9">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-xs font-bold uppercase tracking-[.16em] text-[var(--color-primary)]">Phase 06 · Supplier & Sourcing</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight">Supplier Operations</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Verifikasi pemasok, dokumen, dan penawaran. Harga serta stok ditampilkan dengan timestamp dan masa berlaku.</p></div><span className="inline-flex w-fit items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600"><Truck size={15}/>{suppliers.length} pemasok · {offers.length} penawaran</span></div>
      {error&&<p role="alert" className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      {notice&&<p role="status" className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
      {loading?<div className="mt-8 rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500">Memuat data nyata dari API OtoClinic…</div>:<>
        <section className="mt-8"><div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-bold">Pendaftaran pemasok</h2><span className="text-xs text-slate-500">Tidak ada data contoh</span></div>
          <div className="grid gap-3 lg:grid-cols-2">{suppliers.length===0?<div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">Belum ada pemasok terdaftar.</div>:suppliers.map(s=><article key={s.id} className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-bold">{s.display_name}</h3><p className="mt-1 text-sm text-slate-500">{s.legal_name} · {s.supplier_type}</p><p className="mt-2 text-xs text-slate-500">{s.contact_name??"Kontak belum ada"} · {s.contact_email??"Email belum ada"} · {s.contact_phone??"Telepon belum ada"}</p>{s.business_registration_number&&<p className="mt-2 text-xs text-slate-500">Nomor registrasi: {s.business_registration_number}</p>}</div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold">{statusLabel[s.status]??s.status}</span></div>{s.review_note&&<p className="mt-3 rounded-lg bg-rose-50 p-2 text-xs text-rose-800">Catatan: {s.review_note}</p>}<div className="mt-4 flex flex-wrap gap-2">{s.status==="pending_review"&&canReview&&<><button disabled={!!busy} onClick={()=>void mutate("approve_supplier",{supplier_id:s.id})} className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[var(--color-primary)] px-3 text-xs font-bold text-white disabled:opacity-50"><Check size={14}/> Verifikasi pemasok</button><button disabled={!!busy||!reason.trim()} onClick={()=>void mutate("reject_supplier",{supplier_id:s.id},{reason})} className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-rose-200 px-3 text-xs font-bold text-rose-700 disabled:opacity-50"><X size={14}/> Tolak</button></>}{s.status==="active"&&canReview&&<button disabled={!!busy||!reason.trim()} onClick={()=>void mutate("suspend_supplier",{supplier_id:s.id},{reason})} className="min-h-10 rounded-lg border border-rose-200 px-3 text-xs font-bold text-rose-700 disabled:opacity-50">Tangguhkan</button>}</div></article>)}</div>
        </section>
        {canReadDocuments&&<section className="mt-8"><div className="mb-3 flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-bold">Dokumen menunggu review</h2><p className="text-xs text-slate-500">Buka signed URL berumur 2 menit</p></div>
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">{documents.length===0?<p className="p-6 text-sm text-slate-500">Tidak ada dokumen menunggu review.</p>:<div className="divide-y divide-slate-100">{documents.map(d=><div key={d.id} className="flex flex-col justify-between gap-3 p-4 sm:flex-row sm:items-center"><div><p className="font-semibold">{d.original_filename}</p><p className="mt-1 text-xs text-slate-500">{d.suppliers?.display_name??d.supplier_id} · {d.document_type} · {(d.file_size_bytes/1024).toFixed(0)} KB</p><p className="mt-1 text-xs text-slate-500">Diunggah: {date(d.created_at)} · Kedaluwarsa: {date(d.expires_at)}</p></div><div className="flex flex-wrap gap-2"><button onClick={()=>void openDocument(d)} className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-200 px-3 text-xs font-bold"><ExternalLink size={14}/> Buka</button>{canReview&&<><button disabled={!!busy} onClick={()=>void mutate("review_supplier_document",{document_id:d.id},{status:"verified"})} className="min-h-10 rounded-lg bg-[var(--color-primary)] px-3 text-xs font-bold text-white disabled:opacity-50">Verifikasi</button><button disabled={!!busy||!reason.trim()} onClick={()=>void mutate("review_supplier_document",{document_id:d.id},{status:"rejected",reason})} className="min-h-10 rounded-lg border border-rose-200 px-3 text-xs font-bold text-rose-700 disabled:opacity-50">Tolak</button></>}</div></div>)}</div>}</div>
        </section>}
        <section className="mt-8"><div className="mb-3 flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-bold">Penawaran dan sourcing</h2><p className="text-xs text-slate-500">Harga IDR · stok perlu diperbarui setiap 24 jam</p></div>
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">{offers.length===0?<p className="p-6 text-sm text-slate-500">Belum ada penawaran pemasok.</p>:<div className="divide-y divide-slate-100">{offers.map(o=>{const stale=!o.stock_checked_at||Date.now()-new Date(o.stock_checked_at).getTime()>24*60*60*1000;const expired=!o.quote_expires_at||new Date(o.quote_expires_at).getTime()<=Date.now();const evidenceParts=[o.source_evidence?.reference,o.source_evidence?.part_number,o.source_evidence?.notes].filter((value):value is string=>typeof value==="string"&&value.trim().length>0);return <article key={o.id} className="p-4 sm:p-5"><div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start"><div><div className="flex flex-wrap items-center gap-2"><h3 className="font-bold">{o.supplier_sku??"SKU belum diberikan"}</h3><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold">{statusLabel[o.status]??o.status}</span>{stale&&<span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">Stok usang</span>}{expired&&<span className="rounded-full bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-800">Quotation kedaluwarsa</span>}</div><p className="mt-1 text-sm text-slate-500">{o.suppliers?.display_name??o.supplier_id} · {o.condition}</p><p className="mt-2 text-sm font-semibold">{money(o.unit_cost)} biaya supplier · {money(o.asking_price)} harga penawaran</p><p className="mt-1 text-xs text-slate-500">Stok: {o.stock_quantity} · Dilaporkan supplier: {date(o.stock_checked_at)} · Quote berakhir: {date(o.quote_expires_at)}</p><p className="mt-1 text-xs text-slate-500">Lead time: {o.lead_time_days} hari · MOQ: {o.minimum_order_quantity} · Garansi: {o.warranty_days} hari</p>{evidenceParts.length>0&&<p className="mt-2 break-words text-xs text-slate-600">Bukti: {evidenceParts.join(" · ")}</p>}{o.source_url&&<a href={o.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs font-semibold text-[var(--color-primary)] underline">Bukti sumber</a>}</div><div className="flex flex-wrap gap-2"><button disabled={candidateBusy===o.id} onClick={()=>void findCandidates(o.id)} className="min-h-10 rounded-lg border border-slate-200 px-3 text-xs font-bold disabled:opacity-50">{candidateBusy===o.id?"Mencocokkan…":"Cari kandidat katalog"}</button>{o.status==="pending_review"&&<><button disabled={!!busy||stale||expired} onClick={()=>void mutate("approve_offer",{offer_id:o.id})} className="min-h-10 rounded-lg bg-[var(--color-primary)] px-3 text-xs font-bold text-white disabled:opacity-50">Setujui</button><button disabled={!!busy||!reason.trim()} onClick={()=>void mutate("reject_offer",{offer_id:o.id},{reason})} className="min-h-10 rounded-lg border border-rose-200 px-3 text-xs font-bold text-rose-700 disabled:opacity-50">Tolak</button></>}{o.status==="active"&&<button disabled={!!busy} onClick={()=>void mutate("expire_offer",{offer_id:o.id})} className="min-h-10 rounded-lg border border-slate-200 px-3 text-xs font-bold">Tandai kedaluwarsa</button>}</div></div>{candidateResults[o.id]&&<div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3"><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Kandidat identifikasi · tidak mengonfirmasi fitment</p>{candidateResults[o.id].length===0?<p className="mt-2 text-sm text-slate-500">Tidak ada SKU/nomor part yang cocok persis. Jangan menautkan secara otomatis.</p>:<div className="mt-2 space-y-2">{candidateResults[o.id].map(c=><div key={c.product_id} className="flex flex-col justify-between gap-2 rounded-lg border border-slate-200 bg-white p-3 sm:flex-row sm:items-center"><div><p className="text-sm font-semibold">{c.name}</p><p className="mt-1 text-xs text-slate-500">SKU {c.sku??"—"} · Part {c.part_number??"—"} · {c.match_reason.replaceAll("_"," ")} · {c.status}</p><p className="mt-1 text-xs text-slate-500">{c.fitment_verified?"Ada fitment terverifikasi":"Fitment belum terverifikasi"}</p></div><button disabled={!!busy||o.product_id===c.product_id} onClick={()=>void mutate("match_offer_product",{offer_id:o.id},{product_id:c.product_id})} className="min-h-9 shrink-0 rounded-lg border border-slate-200 px-3 text-xs font-bold disabled:opacity-50">{o.product_id===c.product_id?"Sudah ditautkan":"Tautkan kandidat"}</button></div>)}</div>}</div>}</article>})}</div>}</div>
        </section>
        {canReadAudit&&<section className="mt-8 rounded-2xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-bold">Audit supplier terbaru</h2><span className="text-xs text-slate-500">50 event terbaru · metadata saja</span></div>{auditEvents.length===0?<p className="mt-3 text-sm text-slate-500">Belum ada event audit supplier.</p>:<div className="mt-3 divide-y divide-slate-100">{auditEvents.map(event=><article key={event.id} className="py-3"><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold">{event.action}</span><span className="text-xs text-slate-500">{event.entity_type}</span><span className="ml-auto text-xs text-slate-500">{date(event.created_at)}</span></div><p className="mt-1 break-all text-xs text-slate-500">Entity: {event.entity_id??"—"} · Actor: {event.actor_user_id}</p><p className="mt-1 break-all text-xs text-slate-500">Request: {event.request_id??"—"}</p></article>)}</div>}</section>}
        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-4"><label className="block text-sm font-semibold">Alasan penolakan / penangguhan <span className="font-normal text-slate-500">(wajib untuk aksi tersebut)</span><input value={reason} onChange={e=>setReason(e.target.value)} maxLength={1000} placeholder="Tulis alasan yang akan masuk audit log" className="mt-2 min-h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-[var(--color-primary)]"/></label><p className="mt-2 text-xs text-slate-500">Seluruh aksi mutasi menggunakan FastAPI, idempotency key, validasi status, dan audit database. Tidak ada perubahan status dari UI langsung.</p></section>
      </>}
      <footer className="mt-8 flex flex-wrap gap-4 border-t border-slate-200 pt-5 text-sm"><Link href="/admin" className="font-semibold text-[var(--color-primary)]">Workspace</Link><Link href="/catalog" className="font-semibold text-[var(--color-primary)]">Katalog & fitment</Link></footer>
    </div>
  </main>;
}
