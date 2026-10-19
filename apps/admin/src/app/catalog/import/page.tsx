"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, FileSpreadsheet, Upload } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "https://otoclinic-api-production.up.railway.app";
const CONDITIONS = new Set(["unknown", "new_oem", "new_aftermarket", "used", "refurbished", "remanufactured", "damaged_for_parts"]);
const HEADERS = ["sku","slug","name","description","brand","part_number","category","condition","condition_grade","package_quantity","warranty_days","retail_price","weight_grams","source_rights_evidence","fitment_variant_id","fitment_evidence_url","fitment_evidence_note","marketplace","marketplace_listing_url","marketplace_image_url","marketplace_price_low_idr","marketplace_price_high_idr","marketplace_sales_signal","marketplace_seller","marketplace_rating_signal","marketplace_evidence_note"];
type Row = Record<string,string>;
type CheckedRow = { line:number; values:Row; errors:string[] };
type Outcome = {line:number;sku:string;status:"success"|"partial"|"error"|"invalid";message:string;productId?:string};

function parseCsv(text:string):string[][] {
 const rows:string[][]=[]; let row:string[]=[]; let field=""; let quoted=false;
 for(let i=0;i<text.length;i++){
  const ch=text[i];
  if(quoted){if(ch==='"'&&text[i+1]==='"'){field+='"';i++;}else if(ch==='"'){quoted=false;}else{field+=ch;}}
  else if(ch==='"'&&field.length===0){quoted=true;}
  else if(ch===","){row.push(field);field="";}
  else if(ch==="\n"){row.push(field.replace(/\r$/,""));rows.push(row);row=[];field="";}
  else{field+=ch;}
 }
 if(quoted)throw new Error("CSV memiliki tanda kutip yang belum ditutup.");
 if(field.length||row.length){row.push(field.replace(/\r$/,""));rows.push(row);}
 return rows.filter(r=>r.some(v=>v.trim()!==""));
}
function slugify(value:string){return value.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,110);}
function validateRows(text:string):CheckedRow[]{
 const matrix=parseCsv(text); if(matrix.length<2)throw new Error("CSV harus berisi header dan minimal satu baris produk.");
 const headers=matrix[0].map(v=>v.trim().toLowerCase().replace(/^\uFEFF/,""));
 const required=["sku","name","category","condition","retail_price","weight_grams","source_rights_evidence"];
 const missing=required.filter(h=>!headers.includes(h)); if(missing.length)throw new Error("Kolom wajib belum ada: "+missing.join(", "));
 const seen=new Set<string>();
 return matrix.slice(1).map((cells,index)=>{
  const values:Row={};headers.forEach((h,i)=>{if(h)values[h]=(cells[i]??"").trim();});
  const errors:string[]=[];const line=index+2;
  for(const key of required)if(!values[key])errors.push(key+" wajib diisi");
  if(values.condition&&!CONDITIONS.has(values.condition))errors.push("condition tidak dikenal");
  if(values.sku){const key=values.sku.toLowerCase();if(seen.has(key))errors.push("SKU duplikat di file");seen.add(key);}
  if(values.retail_price!==undefined&&values.retail_price!==""){const n=Number(values.retail_price);if(!Number.isFinite(n)||n<0)errors.push("retail_price harus angka IDR >= 0");}
  if(values.weight_grams!==undefined&&values.weight_grams!==""){const n=Number(values.weight_grams);if(!Number.isInteger(n)||n<1||n>1000000)errors.push("weight_grams harus bilangan 1–1.000.000");}
  if(values.package_quantity){const n=Number(values.package_quantity);if(!Number.isInteger(n)||n<1)errors.push("package_quantity harus bilangan minimal 1");}
  if(values.warranty_days){const n=Number(values.warranty_days);if(!Number.isInteger(n)||n<0)errors.push("warranty_days harus bilangan >= 0");}
  if(values.fitment_variant_id&&!values.fitment_evidence_url&&!values.fitment_evidence_note)errors.push("fitment memerlukan URL bukti atau catatan");
  if(values.marketplace_image_url&&!values.marketplace_listing_url)errors.push("marketplace_listing_url wajib jika URL foto marketplace diisi");
  if(!values.slug&&values.name)values.slug=slugify(values.name)+"-"+(values.sku||"part").toLowerCase().replace(/[^a-z0-9-]/g,"-").slice(0,24);
  if(values.slug&&!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(values.slug))errors.push("slug harus berupa huruf kecil, angka, dan tanda hubung");
  return {line,values,errors};
 });
}
function downloadTemplate(){
 const blob=new Blob(["\\uFEFF"+HEADERS.join(",")+"\\r\\n"],{type:"text/csv;charset=utf-8;"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="otoclinic-product-import-template.csv";a.click();URL.revokeObjectURL(url);
}

export default function CatalogImportPage(){
 const router=useRouter();const [token,setToken]=useState("");const [role,setRole]=useState("");const [fileName,setFileName]=useState("");const [rows,setRows]=useState<CheckedRow[]>([]);const [parseError,setParseError]=useState("");const [busy,setBusy]=useState(false);const [outcomes,setOutcomes]=useState<Outcome[]>([]);const [notice,setNotice]=useState("");
 useEffect(()=>{let alive=true;void(async()=>{const client=getSupabaseBrowserClient();if(!client){setParseError("Supabase Auth belum dikonfigurasi.");return;}const {data,error}=await client.auth.getSession();if(error||!data.session){router.replace("/login");return;}if(!alive)return;setToken(data.session.access_token);const r=await fetch(API+"/v1/auth/me",{headers:{Authorization:"Bearer "+data.session.access_token}});const body=await r.json().catch(()=>({}));if(!r.ok){setParseError("Identitas staf tidak dapat diverifikasi melalui API.");return;}setRole(String(body.role??body.profile?.role??""));})();return()=>{alive=false}},[router]);
 const validCount=useMemo(()=>rows.filter(r=>!r.errors.length).length,[rows]);
 async function chooseFile(file:File|null){setRows([]);setOutcomes([]);setNotice("");setParseError("");if(!file)return;if(file.size>5*1024*1024){setParseError("Ukuran CSV maksimal 5 MB.");return;}try{const checked=validateRows(await file.text());if(checked.length>100)throw new Error("Maksimal 100 produk per impor. Pecah file lebih besar menjadi beberapa batch.");setFileName(file.name);setRows(checked);}catch(e){setParseError(e instanceof Error?e.message:"CSV tidak dapat dibaca.");}}
 async function applyImport(){
  if(!token||!rows.length||validCount===0)return;
  setBusy(true);setParseError("");setNotice("");setOutcomes([]);
  const results:Outcome[]=[];
  try{
   for(const item of rows){
    const v=item.values;const sku=v.sku||"";
    if(item.errors.length){results.push({line:item.line,sku,status:"invalid",message:item.errors.join("; ")});setOutcomes([...results]);continue;}
    let productId="";
    try{
     const payload:Record<string,unknown>={sku,slug:v.slug||slugify(v.name)+"-"+sku.toLowerCase().replace(/[^a-z0-9-]/g,"-").slice(0,24),name:v.name,description:v.description||null,brand:v.brand||null,part_number:v.part_number||null,category:v.category,condition:v.condition,condition_grade:v.condition_grade||null,package_quantity:Number(v.package_quantity||1),warranty_days:Number(v.warranty_days||0),retail_price:Number(v.retail_price),source_rights_evidence:[v.source_rights_evidence,v.marketplace_listing_url?"Listing sumber "+(v.marketplace||"marketplace")+": "+v.marketplace_listing_url:null,v.marketplace_evidence_note?"Sinyal riset: "+v.marketplace_evidence_note:null,v.marketplace_price_low_idr||v.marketplace_price_high_idr?"Rentang harga teramati IDR "+(v.marketplace_price_low_idr||"?")+"–"+(v.marketplace_price_high_idr||"?")+"; sinyal terjual/rating bukan jaminan stok atau kualitas: "+[v.marketplace_sales_signal,v.marketplace_rating_signal,v.marketplace_seller].filter(Boolean).join(" | "):null].filter(Boolean).join(" | ")};
     const created=await fetch(API+"/v1/admin/catalog/mutations",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({action:"create_product",payload})});
     const createdBody=await created.json().catch(()=>({}));if(!created.ok)throw new Error(createdBody.detail||"API menolak pembuatan draft.");
     productId=String(createdBody.result?.product?.id||"");if(!productId)throw new Error("API tidak mengembalikan ID produk; periksa hasil di katalog sebelum mengulang.");
     const weight=await fetch(API+"/v1/admin/catalog/products/"+productId+"/shipping-weight",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({weight_grams:Number(v.weight_grams)})});
     const weightBody=await weight.json().catch(()=>({}));if(!weight.ok)throw new Error("Produk tersimpan sebagai draft, tetapi berat gagal disimpan: "+(weightBody.detail||"API menolak berat."));
     if(v.fitment_variant_id){
      const fit=await fetch(API+"/v1/admin/catalog/mutations",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({action:"save_fitment",product_id:productId,payload:{variant_id:v.fitment_variant_id,evidence_url:v.fitment_evidence_url||null,evidence_note:v.fitment_evidence_note||null}})});
      const fitBody=await fit.json().catch(()=>({}));if(!fit.ok)throw new Error("Produk dan berat tersimpan; fitment belum tersimpan: "+(fitBody.detail||"API menolak fitment."));
     }
     if(v.marketplace_image_url){
      const media=await fetch(API+"/v1/admin/catalog/products/"+productId+"/media/import-marketplace",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify({image_url:v.marketplace_image_url,source_listing_url:v.marketplace_listing_url,alt_text:"Foto referensi draft: "+v.name})});
      const mediaBody=await media.json().catch(()=>({}));if(!media.ok)throw new Error("Produk tersimpan sebagai draft; foto referensi gagal diimpor: "+(mediaBody.detail||"API menolak foto."));
     }
     results.push({line:item.line,sku,status:"success",message:"Draft dibuat; berat tersimpan"+(v.fitment_variant_id?"; fitment masuk review":"")+".",productId});
    }catch(e){results.push({line:item.line,sku,status:productId?"partial":"error",message:e instanceof Error?e.message:"Impor baris gagal.",productId:productId||undefined});}
    setOutcomes([...results]);
   }
   const ok=results.filter(r=>r.status==="success").length;const bad=results.filter(r=>r.status!=="success").length;setNotice("Batch selesai: "+ok+" berhasil, "+bad+" perlu ditinjau. Semua produk yang dibuat tetap berstatus draft; tidak ada produk yang otomatis dipublikasikan.");
  }finally{setBusy(false);}
 }
 return <main className="min-h-screen bg-[var(--color-canvas)] text-slate-900"><header className="border-b border-slate-200 bg-white"><div className="mx-auto flex min-h-16 max-w-5xl items-center justify-between gap-3 px-4 sm:px-6"><Link href="/catalog" className="inline-flex items-center gap-2 text-sm font-bold text-slate-600"><ArrowLeft size={17}/> Kembali ke katalog</Link><span className="text-xs font-semibold text-slate-500">Role API: {role||"memeriksa…"}</span></div></header>
 <div className="mx-auto max-w-5xl px-4 py-7 sm:px-6 sm:py-10"><p className="text-xs font-extrabold uppercase tracking-[.16em] text-[var(--color-primary)]">Catalog operations</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight">Impor produk dari CSV</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">Impor memakai sesi staf dan FastAPI. Setiap baris divalidasi, disimpan sebagai draft dengan audit/idempotensi, lalu berat paket diikat melalui endpoint FastAPI. Stok dan foto tetap mengikuti alur inventaris/media terpisah. Impor tidak pernah menerbitkan produk otomatis.</p>
 <div className="mt-6 grid gap-4 md:grid-cols-2"><section className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center gap-2 font-bold"><FileSpreadsheet size={19}/> Format file</div><p className="mt-2 text-sm text-slate-600">CSV UTF-8 maksimal 5 MB dan 100 produk per batch. Kolom wajib: sku, name, category, condition, retail_price, weight_grams, source_rights_evidence. Kolom slug boleh dikosongkan dan akan dibuat dari nama + SKU.</p><button type="button" onClick={downloadTemplate} className="mt-4 inline-flex min-h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-bold"><Download size={16}/> Unduh template CSV</button></section>
 <section className="rounded-2xl border border-slate-200 bg-white p-5"><div className="font-bold">Pilih file impor</div><p className="mt-2 text-sm text-slate-600">Produk selalu dibuat sebagai draft. Condition `unknown` diperbolehkan hanya pada draft; database memblokir pengajuan review sampai kondisi diverifikasi. Foto referensi dari marketplace disalin ke Storage privat dengan hak penggunaan belum diverifikasi dan review pending; foto tidak boleh dipublikasikan sebelum izin/lisensi terbukti. Fitment yang diisi lewat CSV hanya masuk status review. Stok awal dicatat terpisah melalui modul Inventaris setelah produk dipublikasikan. Kolom opsional marketplace_image_url dan marketplace_listing_url akan menyalin foto referensi ke Storage privat dengan review pending.</p><label className="mt-4 block text-sm font-semibold">File CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={e=>void chooseFile(e.target.files?.[0]??null)} className="mt-2 block min-h-11 w-full rounded-xl border border-slate-200 p-2 text-sm"/></label>{fileName&&<p className="mt-2 text-xs text-slate-500">File: {fileName}</p>}</section></div>
 {parseError&&<p role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{parseError}</p>}
 {rows.length>0&&<section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white"><div className="flex flex-col gap-2 border-b border-slate-100 p-4 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-extrabold">Pratinjau validasi</h2><p className="mt-1 text-sm text-slate-500">{rows.length} baris · {validCount} valid · {rows.length-validCount} bermasalah</p></div><button type="button" disabled={busy||validCount===0} onClick={()=>void applyImport()} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 font-bold text-white disabled:opacity-50"><Upload size={16}/>{busy?"Memproses batch…":"Impor baris valid"}</button></div><div className="max-h-[26rem] overflow-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="p-3">Baris</th><th className="p-3">SKU</th><th className="p-3">Produk</th><th className="p-3">Harga</th><th className="p-3">Berat</th><th className="p-3">Validasi</th></tr></thead><tbody>{rows.map(r=><tr key={r.line} className="border-t border-slate-100"><td className="p-3">{r.line}</td><td className="p-3 font-mono text-xs">{r.values.sku||"—"}</td><td className="p-3">{r.values.name||"—"}<span className="block text-xs text-slate-500">{r.values.brand||""} {r.values.part_number||""}</span></td><td className="p-3 tabular-nums">{r.values.retail_price||"—"}</td><td className="p-3 tabular-nums">{r.values.weight_grams||"—"} g</td><td className="p-3">{r.errors.length?<span className="text-xs text-rose-700">{r.errors.join("; ")}</span>:<span className="text-xs font-bold text-emerald-700">Valid</span>}</td></tr>)}</tbody></table></div></section>}
 {notice&&<p role="status" className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}
 {outcomes.length>0&&<section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-extrabold">Hasil impor</h2><div className="mt-3 divide-y divide-slate-100">{outcomes.map((o,i)=><div key={o.line+"-"+i} className="py-3"><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs">{o.sku||"—"}</span><span className={"rounded-full px-2 py-1 text-xs font-bold "+(o.status==="success"?"bg-emerald-50 text-emerald-700":o.status==="partial"?"bg-amber-50 text-amber-800":"bg-rose-50 text-rose-700")}>{o.status}</span><span className="text-xs text-slate-500">Baris {o.line}</span></div><p className="mt-1 text-sm text-slate-600">{o.message}</p>{o.productId&&<p className="mt-1 font-mono text-xs text-slate-400">{o.productId}</p>}</div>)}</div><Link href="/catalog" className="mt-4 inline-flex min-h-10 items-center rounded-xl border border-slate-200 px-4 text-sm font-bold">Kembali ke katalog</Link></section>}
 <section className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"><strong>Jangan mengarang data.</strong> Gunakan harga yang terlihat pada sumber produk pada tanggal pengambilan, SKU/part number yang bisa diverifikasi, berat paket aktual, dan bukti sumber. Produk tanpa foto yang haknya jelas, fitment terverifikasi, stok yang dicatat, dan review yang diperlukan tetap tidak boleh dipublikasikan.</section></div></main>;
}
