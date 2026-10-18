"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, FileUp, LogOut, RefreshCw, ShieldCheck, Truck } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type Supplier = { id:string; legal_name:string; display_name:string; supplier_type:string; status:string; review_note:string|null; contact_email:string|null; };
type DocumentRow = { id:string; document_type:string; storage_path:string; original_filename:string; content_type:string; file_size_bytes:number; status:string; review_note:string|null; created_at:string; expires_at:string|null; };
type Offer = { id:string; supplier_sku:string|null; condition:string; unit_cost:number|null; asking_price:number|null; stock_quantity:number; stock_checked_at:string|null; quote_expires_at:string|null; status:string; lead_time_days:number; minimum_order_quantity:number; warranty_days:number; source_url:string|null; source_verified_at:string|null; };

const API=process.env.NEXT_PUBLIC_API_BASE_URL??"https://otoclinic-api-production.up.railway.app";
const BUCKET="supplier-verification-documents";
const labels:Record<string,string>={pending_review:"Menunggu verifikasi",active:"Aktif",suspended:"Ditangguhkan",rejected:"Ditolak",verified:"Terverifikasi",expired:"Kedaluwarsa",unavailable:"Tidak tersedia"};
const docTypes=[["business_registration","NIB / registrasi usaha"],["tax_registration","NPWP / pajak"],["business_license","Izin usaha"],["identity_authorization","Identitas / surat kuasa"],["source_rights","Bukti hak sumber barang"],["other","Dokumen lain"]];

export default function SupplierPortalPage(){
 const supabase=getSupabaseBrowserClient();
 const [loading,setLoading]=useState(true);
 const [authenticated,setAuthenticated]=useState(false);
 const [authorized,setAuthorized]=useState(false);
 const [token,setToken]=useState("");
 const [userId,setUserId]=useState("");
 const [supplier,setSupplier]=useState<Supplier|null>(null);
 const [documents,setDocuments]=useState<DocumentRow[]>([]);
 const [offers,setOffers]=useState<Offer[]>([]);
 const [error,setError]=useState("");
 const [notice,setNotice]=useState("");
 const [busy,setBusy]=useState(false);
 const [email,setEmail]=useState("");
 const [password,setPassword]=useState("");
 const [legalName,setLegalName]=useState("");
 const [displayName,setDisplayName]=useState("");
 const [supplierType,setSupplierType]=useState("supplier");
 const [contactName,setContactName]=useState("");
 const [contactEmail,setContactEmail]=useState("");
 const [contactPhone,setContactPhone]=useState("");
 const [registrationNumber,setRegistrationNumber]=useState("");
 const [websiteUrl,setWebsiteUrl]=useState("");
 const [city,setCity]=useState("");
 const [province,setProvince]=useState("");
 const [documentType,setDocumentType]=useState("business_registration");
 const [documentExpiry,setDocumentExpiry]=useState("");
 const [selectedFile,setSelectedFile]=useState<File|null>(null);
 const [supplierSku,setSupplierSku]=useState("");
 const [sourceUrl,setSourceUrl]=useState("");
 const [evidenceReference,setEvidenceReference]=useState("");
 const [evidenceNote,setEvidenceNote]=useState("");
 const [condition,setCondition]=useState("new_aftermarket");
 const [unitCost,setUnitCost]=useState("");
 const [askingPrice,setAskingPrice]=useState("");
 const [stockQuantity,setStockQuantity]=useState("1");
 const [quoteExpiry,setQuoteExpiry]=useState("");
 const [leadTimeDays,setLeadTimeDays]=useState("2");
 const [moq,setMoq]=useState("1");
 const [warrantyDays,setWarrantyDays]=useState("0");

 const apiFetch=useCallback(async(path:string,init:RequestInit={})=>{
   const headers=new Headers(init.headers);
   headers.set("Authorization","Bearer "+token);
   if(init.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
   const response=await fetch(API+path,{...init,headers,cache:"no-store"});
   const body=await response.json().catch(()=>({}));
   if(!response.ok)throw new Error(body.detail??"Permintaan supplier gagal (HTTP "+response.status+").");
   return body;
 },[token]);

 const load=useCallback(async()=>{
   setLoading(true);setError("");
   if(!supabase){setError("Supabase belum dikonfigurasi pada environment Web.");setLoading(false);return;}
   const {data:{session},error:sessionError}=await supabase.auth.getSession();
   if(sessionError){setError("Sesi tidak dapat dibaca. Silakan masuk kembali.");setLoading(false);return;}
   if(!session){setAuthenticated(false);setAuthorized(false);setLoading(false);return;}
   setAuthenticated(true);setToken(session.access_token);setUserId(session.user.id);
   const {data:profile,error:profileError}=await supabase.from("user_profiles").select("role,is_active").eq("id",session.user.id).maybeSingle();
   if(profileError||!profile?.is_active||!["customer","supplier"].includes(profile.role??"")){
     setAuthorized(false);setError("Portal pemasok membutuhkan akun aktif dengan role customer atau supplier.");setLoading(false);return;
   }
   setAuthorized(true);
   try{
     const profileResult=await fetch(API+"/v1/supplier/profile",{headers:{Authorization:"Bearer "+session.access_token},cache:"no-store"});
     const profileBody=await profileResult.json().catch(()=>({}));
     if(!profileResult.ok)throw new Error(profileBody.detail??"Profil pemasok tidak dapat dimuat.");
     const current=(profileBody.supplier??null) as Supplier|null;
     setSupplier(current);
     if(current){
       const headers={Authorization:"Bearer "+session.access_token};
       const [docRes,offerRes]=await Promise.all([
         fetch(API+"/v1/supplier/documents",{headers,cache:"no-store"}),
         fetch(API+"/v1/supplier/offers",{headers,cache:"no-store"}),
       ]);
       const [docBody,offerBody]=await Promise.all([docRes.json().catch(()=>({})),offerRes.json().catch(()=>({}))]);
       if(!docRes.ok)throw new Error(docBody.detail??"Dokumen pemasok tidak dapat dimuat.");
       if(!offerRes.ok)throw new Error(offerBody.detail??"Penawaran pemasok tidak dapat dimuat.");
       setDocuments((docBody.items??[]) as DocumentRow[]);
       setOffers((offerBody.items??[]) as Offer[]);
     }else{setDocuments([]);setOffers([]);}
   }catch(e){setError(e instanceof Error?e.message:"Data pemasok gagal dimuat.");}
   finally{setLoading(false);}
 },[supabase]);

 useEffect(()=>{void load();},[load]);

 async function signIn(e:FormEvent){
   e.preventDefault();if(!supabase)return;setBusy(true);setError("");setNotice("");
   const {error:authError}=await supabase.auth.signInWithPassword({email,password});
   if(authError){setError(authError.message);setBusy(false);return;}
   setPassword("");await load();setBusy(false);
 }

 async function signOut(){
   if(supabase)await supabase.auth.signOut();
   setAuthenticated(false);setAuthorized(false);setSupplier(null);setDocuments([]);setOffers([]);setToken("");
 }

 async function submitOnboarding(e:FormEvent){
   e.preventDefault();setBusy(true);setError("");setNotice("");
   try{
     await apiFetch("/v1/supplier/onboarding",{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({
       legal_name:legalName,display_name:displayName,supplier_type:supplierType,contact_name:contactName||undefined,
       contact_email:contactEmail||undefined,contact_phone:contactPhone||undefined,
       business_registration_number:registrationNumber||undefined,website_url:websiteUrl||undefined,
       address:{city:city||undefined,province:province||undefined,country:"Indonesia"},
     })});
     setNotice("Pendaftaran terkirim. Status tetap menunggu verifikasi sampai dokumen diperiksa tim OtoClinic.");
     await load();
   }catch(e){setError(e instanceof Error?e.message:"Pendaftaran pemasok gagal.");}
   finally{setBusy(false);}
 }

 async function uploadDocument(e:FormEvent){
   e.preventDefault();
   if(!supabase||!supplier||!selectedFile)return;
   const file=selectedFile;
   if(!["application/pdf","image/jpeg","image/png"].includes(file.type)){setError("Format dokumen harus PDF, JPG, atau PNG.");return;}
   if(file.size<1||file.size>10*1024*1024){setError("Ukuran file maksimal 10 MB.");return;}
   setBusy(true);setError("");setNotice("");
   try{
     const safeName=file.name.replace(/[^a-zA-Z0-9._-]/g,"_");
     const path=userId+"/"+supplier.id+"/"+crypto.randomUUID()+"-"+safeName;
     const {error:uploadError}=await supabase.storage.from(BUCKET).upload(path,file,{contentType:file.type,upsert:false});
     if(uploadError)throw new Error(uploadError.message);
     const digest=await crypto.subtle.digest("SHA-256",await file.arrayBuffer());
     const sha256=Array.from(new Uint8Array(digest)).map(b=>b.toString(16).padStart(2,"0")).join("");
     await apiFetch("/v1/supplier/documents",{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({
       document_type:documentType,storage_path:path,original_filename:file.name,content_type:file.type,
       file_size_bytes:file.size,sha256,expires_at:documentExpiry?new Date(documentExpiry).toISOString():undefined,
     })});
     setSelectedFile(null);setDocumentExpiry("");setNotice("Dokumen diunggah ke Storage privat dan masuk antrean verifikasi.");
     await load();
   }catch(e){setError(e instanceof Error?e.message:"Dokumen gagal diunggah atau didaftarkan. Jangan unggah ulang dengan nama berbeda sebelum memeriksa status.");}
   finally{setBusy(false);}
 }

 async function submitOffer(e:FormEvent){
   e.preventDefault();setBusy(true);setError("");setNotice("");
   try{
     await apiFetch("/v1/supplier/offers",{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({
       supplier_sku:supplierSku||undefined,source_url:sourceUrl||undefined,
       source_evidence:{type:"supplier_quote",reference:evidenceReference,notes:evidenceNote,submitted_at:new Date().toISOString()},
       condition,unit_cost:unitCost,asking_price:askingPrice||undefined,stock_quantity:Number(stockQuantity),
       quote_expires_at:new Date(quoteExpiry).toISOString(),lead_time_days:Number(leadTimeDays),
       minimum_order_quantity:Number(moq),warranty_days:Number(warrantyDays),
     })});
     setNotice("Penawaran tersimpan dan menunggu review. Stok tercatat sebagai laporan pemasok pada waktu pengiriman.");
     setSupplierSku("");setSourceUrl("");setEvidenceReference("");setEvidenceNote("");setUnitCost("");setAskingPrice("");
     await load();
   }catch(e){setError(e instanceof Error?e.message:"Penawaran pemasok gagal.");}
   finally{setBusy(false);}
 }

 async function openOwnDocument(doc:DocumentRow){
   if(!supabase)return;
   const {data,error:storageError}=await supabase.storage.from(BUCKET).createSignedUrl(doc.storage_path,120);
   if(storageError||!data?.signedUrl){setError("Dokumen tidak dapat dibuka.");return;}
   window.open(data.signedUrl,"_blank","noopener,noreferrer");
 }

 const money=(value:number|null)=>value===null?"—":new Intl.NumberFormat("id-ID",{style:"currency",currency:"IDR",maximumFractionDigits:0}).format(value);
 const date=(value:string|null)=>value?new Date(value).toLocaleString("id-ID",{dateStyle:"medium",timeStyle:"short"}):"—";

 return <main className="min-h-screen bg-[var(--color-canvas)] text-[var(--color-text)]">
  <header className="border-b border-[var(--color-border)] bg-white"><div className="mx-auto flex min-h-[68px] max-w-6xl items-center justify-between gap-3 px-4 sm:px-6"><Link href="/" className="inline-flex items-center gap-2 text-sm font-bold"><ArrowLeft size={17}/> OtoClinic</Link><div className="flex gap-2">{authenticated&&<button onClick={()=>void load()} disabled={loading} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-xs font-semibold"><RefreshCw size={14}/> Refresh</button>}{authenticated&&<button onClick={()=>void signOut()} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-xs font-semibold"><LogOut size={14}/> Keluar</button>}</div></div></header>
  <div className="mx-auto max-w-6xl px-4 py-7 sm:px-6 sm:py-10">
   <div className="max-w-3xl"><p className="text-xs font-bold uppercase tracking-[.16em] text-[var(--color-primary)]">Portal Mitra</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">Supplier & Sourcing</h1><p className="mt-3 text-sm leading-6 text-slate-600">Daftarkan usaha, unggah dokumen verifikasi secara privat, dan kirim penawaran dengan bukti sumber, timestamp stok, lead time, serta masa berlaku quotation.</p></div>
   {error&&<p role="alert" className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
   {notice&&<p role="status" className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}
   {loading?<div className="mt-7 rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">Memuat status akun…</div>:!authenticated?<section className="mt-7 max-w-md rounded-2xl border border-slate-200 bg-white p-5 sm:p-7"><h2 className="text-lg font-bold">Masuk untuk melanjutkan</h2><p className="mt-1 text-sm text-slate-500">Gunakan akun OtoClinic yang aktif. Pendaftaran supplier tidak membuat akun atau role secara otomatis.</p><form onSubmit={signIn} className="mt-5 space-y-4"><label className="block text-sm font-semibold">Email<input required type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="block text-sm font-semibold">Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><button disabled={busy} className="min-h-11 w-full rounded-xl bg-[var(--color-primary)] px-4 font-bold text-white disabled:opacity-50">{busy?"Memproses…":"Masuk"}</button></form></section>:!authorized?<section className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900"><ShieldCheck size={20}/><p className="mt-2 font-semibold">Akun belum memiliki profil aktif yang diizinkan.</p><p className="mt-1">Hubungi pengelola OtoClinic untuk mengaktifkan profil terlebih dahulu.</p></section>:!supplier?<section className="mt-7 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7"><div className="flex items-start gap-3"><Truck className="mt-1 text-[var(--color-primary)]" size={22}/><div><h2 className="text-xl font-bold">Pendaftaran pemasok</h2><p className="mt-1 text-sm text-slate-500">Pendaftaran akan berstatus menunggu verifikasi. Tidak ada penawaran yang dipublikasikan sebelum pemasok disetujui.</p></div></div><form onSubmit={submitOnboarding} className="mt-6 grid gap-4 sm:grid-cols-2"><label className="text-sm font-semibold">Nama legal usaha *<input required minLength={2} maxLength={200} value={legalName} onChange={e=>setLegalName(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Nama tampilan *<input required minLength={2} maxLength={160} value={displayName} onChange={e=>setDisplayName(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Jenis pemasok<select value={supplierType} onChange={e=>setSupplierType(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"><option value="supplier">Supplier umum</option><option value="oem_distributor">Distributor OEM</option><option value="aftermarket_distributor">Distributor aftermarket</option><option value="workshop">Bengkel</option><option value="reconditioner">Rekondisi</option><option value="dismantler">Pembongkar / kanibal part</option><option value="individual">Perorangan</option></select></label><label className="text-sm font-semibold">Nomor registrasi usaha<input value={registrationNumber} onChange={e=>setRegistrationNumber(e.target.value)} maxLength={100} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Nama kontak<input value={contactName} onChange={e=>setContactName(e.target.value)} maxLength={160} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Email kontak<input type="email" value={contactEmail} onChange={e=>setContactEmail(e.target.value)} maxLength={254} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Telepon<input value={contactPhone} onChange={e=>setContactPhone(e.target.value)} maxLength={40} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Website<input type="url" value={websiteUrl} onChange={e=>setWebsiteUrl(e.target.value)} maxLength={500} placeholder="https://" className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Kota<input value={city} onChange={e=>setCity(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Provinsi<input value={province} onChange={e=>setProvince(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><div className="sm:col-span-2"><button disabled={busy} className="min-h-11 rounded-xl bg-[var(--color-primary)] px-5 font-bold text-white disabled:opacity-50">{busy?"Mengirim…":"Kirim pendaftaran"}</button></div></form></section>:<>
    <section className="mt-7 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-wide text-slate-500">Status pemasok</p><h2 className="mt-1 text-xl font-bold">{supplier.display_name}</h2><p className="mt-1 text-sm text-slate-500">{supplier.legal_name}</p></div><span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold">{labels[supplier.status]??supplier.status}</span></div>{supplier.review_note&&<p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Catatan review: {supplier.review_note}</p>}{supplier.status!=="active"&&<p className="mt-3 text-sm text-slate-600">Penawaran baru hanya dapat dikirim setelah status pemasok aktif dan dokumen yang diperlukan diverifikasi.</p>}</section>
    <section className="mt-6 grid gap-6 xl:grid-cols-2"><div className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold">Dokumen verifikasi</h2><p className="mt-1 text-sm text-slate-500">PDF, JPG, atau PNG maksimal 10 MB. File disimpan pada bucket privat.</p><form onSubmit={uploadDocument} className="mt-4 space-y-3"><label className="block text-sm font-semibold">Jenis dokumen<select value={documentType} onChange={e=>setDocumentType(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal">{docTypes.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><label className="block text-sm font-semibold">File dokumen<input required type="file" accept=".pdf,image/jpeg,image/png,application/pdf" onChange={e=>setSelectedFile(e.target.files?.[0]??null)} className="mt-1 block w-full rounded-xl border border-slate-200 p-2 text-sm font-normal"/></label><label className="block text-sm font-semibold">Tanggal kedaluwarsa (opsional)<input type="date" value={documentExpiry} onChange={e=>setDocumentExpiry(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><button disabled={busy||!selectedFile} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 font-bold text-white disabled:opacity-50"><FileUp size={16}/>{busy?"Mengunggah…":"Unggah dokumen"}</button></form><div className="mt-5 divide-y divide-slate-100">{documents.length===0?<p className="py-3 text-sm text-slate-500">Belum ada dokumen.</p>:documents.map(d=><div key={d.id} className="flex items-start justify-between gap-3 py-3"><div><p className="text-sm font-semibold">{d.original_filename}</p><p className="mt-1 text-xs text-slate-500">{d.document_type} · {(d.file_size_bytes/1024).toFixed(0)} KB · {date(d.created_at)}</p>{d.review_note&&<p className="mt-1 text-xs text-rose-700">{d.review_note}</p>}</div><button onClick={()=>void openOwnDocument(d)} className="shrink-0 text-xs font-bold text-[var(--color-primary)] underline">Buka</button></div>)}</div></div>
     <div className="rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold">Ajukan penawaran spare part</h2><p className="mt-1 text-sm text-slate-500">Penawaran akan masuk review. Stok dilaporkan dengan timestamp dan kedaluwarsa quote wajib diisi.</p><form onSubmit={submitOffer} className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-sm font-semibold">SKU pemasok<input value={supplierSku} onChange={e=>setSupplierSku(e.target.value)} maxLength={160} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Kondisi<select value={condition} onChange={e=>setCondition(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"><option value="new_oem">Baru OEM</option><option value="new_aftermarket">Baru aftermarket</option><option value="used">Bekas</option><option value="refurbished">Rekondisi</option><option value="remanufactured">Remanufaktur</option><option value="damaged_for_parts">Untuk kanibal part</option></select></label><label className="text-sm font-semibold">Harga beli (IDR) *<input required type="number" min="0" step="1" value={unitCost} onChange={e=>setUnitCost(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Harga penawaran (IDR)<input type="number" min="0" step="1" value={askingPrice} onChange={e=>setAskingPrice(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Jumlah stok *<input required type="number" min="0" step="1" value={stockQuantity} onChange={e=>setStockQuantity(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Quotation berakhir *<input required type="datetime-local" value={quoteExpiry} onChange={e=>setQuoteExpiry(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Lead time (hari)<input required type="number" min="0" max="365" value={leadTimeDays} onChange={e=>setLeadTimeDays(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">MOQ<input required type="number" min="1" value={moq} onChange={e=>setMoq(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">Garansi (hari)<input required type="number" min="0" value={warrantyDays} onChange={e=>setWarrantyDays(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold">URL sumber (opsional)<input type="url" value={sourceUrl} onChange={e=>setSourceUrl(e.target.value)} placeholder="https://" className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold sm:col-span-2">Referensi quotation / bukti sumber *<input required value={evidenceReference} onChange={e=>setEvidenceReference(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><label className="text-sm font-semibold sm:col-span-2">Catatan bukti<input value={evidenceNote} onChange={e=>setEvidenceNote(e.target.value)} maxLength={1000} className="mt-1 min-h-11 w-full rounded-xl border border-slate-200 px-3 font-normal"/></label><div className="sm:col-span-2"><button disabled={busy||supplier.status!=="active"} className="min-h-11 rounded-xl bg-[var(--color-primary)] px-4 font-bold text-white disabled:opacity-50">{busy?"Mengirim…":"Kirim penawaran"}</button>{supplier.status!=="active"&&<p className="mt-2 text-xs text-amber-800">Pemasok harus berstatus aktif sebelum mengirim penawaran.</p>}</div></form></div></section>
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-bold">Riwayat penawaran</h2><div className="mt-3 divide-y divide-slate-100">{offers.length===0?<p className="py-3 text-sm text-slate-500">Belum ada penawaran.</p>:offers.map(o=><article key={o.id} className="flex flex-col justify-between gap-2 py-3 sm:flex-row sm:items-center"><div><p className="font-semibold">{o.supplier_sku??"SKU tidak dicantumkan"} · {o.condition}</p><p className="mt-1 text-xs text-slate-500">{money(o.unit_cost)} · Stok {o.stock_quantity} dicek {date(o.stock_checked_at)} · Quote berakhir {date(o.quote_expires_at)}</p><p className="mt-1 text-xs text-slate-500">Lead time {o.lead_time_days} hari · MOQ {o.minimum_order_quantity} · Garansi {o.warranty_days} hari</p></div><span className="w-fit rounded-full bg-slate-100 px-3 py-1 text-xs font-bold">{labels[o.status]??o.status}</span></article>)}</div></section>
   </>}
   <footer className="mt-8 border-t border-slate-200 pt-5 text-xs text-slate-500">Informasi harga dan stok adalah laporan pemasok sampai bukti diperiksa OtoClinic. Penawaran kedaluwarsa atau stok usang tidak boleh dianggap tersedia.</footer>
  </div>
 </main>;
}
