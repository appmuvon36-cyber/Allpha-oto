"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, PackageCheck, ShieldCheck, ShoppingCart, Wrench } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
type Product = { id:string; sku:string; slug:string; name:string; description:string|null; brand:string|null; part_number:string|null; category:string; condition:string; condition_grade:string|null; package_quantity:number; warranty_days:number; currency:string; retail_price:number|null; fitment_summary:string|null; published_at:string|null };
type Fitment = { id:string; status:string; evidence_url:string|null; evidence_note:string|null; verified_at:string|null; vehicle_variants:{id:string;name:string;year_start:number|null;year_end:number|null;engine_code:string|null;transmission:string|null;vehicle_models:{name:string;vehicle_type:string;vehicle_makes:{name:string}}} };
const conditions:Record<string,string>={new_oem:"Baru · OEM",new_aftermarket:"Baru · aftermarket",used:"Bekas / copotan",refurbished:"Rekondisi",remanufactured:"Remanufaktur",damaged_for_parts:"Rusak · untuk komponen"};
const money=(n:number|null)=>n===null?"Harga belum tersedia":new Intl.NumberFormat("id-ID",{style:"currency",currency:"IDR",maximumFractionDigits:0}).format(n);

export default function ProductDetailPage(){
 const params=useParams<{productId:string}>();
 const id=params.productId;
 const [product,setProduct]=useState<Product|null>(null);
 const [fitments,setFitments]=useState<Fitment[]>([]);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState("");
 useEffect(()=>{let active=true;setLoading(true);setError("");Promise.all([
  fetch(API+"/v1/catalog/products/"+encodeURIComponent(id),{cache:"no-store"}).then(async r=>{const b=await r.json().catch(()=>({}));if(!r.ok)throw new Error(b.detail??"Produk tidak dapat dimuat.");return b.product as Product}),
  fetch(API+"/v1/catalog/products/"+encodeURIComponent(id)+"/fitments",{cache:"no-store"}).then(async r=>{if(!r.ok)throw new Error("Data kecocokan belum dapat dimuat.");return r.json()})
 ]).then(([p,f])=>{if(active){setProduct(p);setFitments((f.items??[]) as Fitment[])}}).catch(e=>{if(active){setProduct(null);setError(e instanceof Error?e.message:"Terjadi gangguan saat memuat produk.")}}).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[id]);
 return <main className="min-h-screen bg-[var(--color-canvas)] text-slate-900">
  <header className="border-b border-[var(--color-border)] bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4"><Link href="/#katalog" className="inline-flex items-center gap-2 text-sm font-bold"><ArrowLeft size={16}/> Kembali ke katalog</Link><Link href="/cart" className="inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-bold"><ShoppingCart size={16}/> Keranjang</Link></div></header>
  <div className="mx-auto max-w-6xl px-4 py-8 sm:py-12">
   {loading?<div role="status" className="rounded-2xl border bg-white p-8">Memuat detail produk…</div>:error||!product?<div role="alert" className="rounded-2xl border border-amber-200 bg-amber-50 p-6"><h1 className="text-xl font-extrabold">Detail produk tidak tersedia</h1><p className="mt-2 text-sm">{error||"Produk tidak ditemukan atau belum dipublikasikan."}</p><Link href="/#katalog" className="mt-4 inline-flex rounded-xl bg-[var(--color-primary)] px-4 py-2.5 font-bold text-white">Kembali mencari</Link></div>:
   <div className="grid gap-6 lg:grid-cols-[1fr_.9fr]">
    <section className="rounded-3xl border border-[var(--color-border)] bg-white p-5 sm:p-8">
     <div className="flex min-h-56 items-center justify-center rounded-2xl bg-slate-50"><Wrench size={64} strokeWidth={1.3} className="text-slate-300"/></div>
     <p className="mt-6 text-xs font-extrabold uppercase tracking-widest text-[var(--color-primary)]">{product.category}</p>
     <h1 className="mt-2 text-2xl font-extrabold leading-tight sm:text-3xl">{product.name}</h1>
     <p className="mt-3 text-sm text-slate-500">{product.brand||"Merek belum dicantumkan"}{product.part_number?" · Nomor part "+product.part_number:""}</p>
     <div className="mt-4 flex flex-wrap gap-2"><span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold">{conditions[product.condition]??product.condition}</span>{product.condition_grade&&<span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold">Grade {product.condition_grade}</span>}</div>
     <p className="mt-5 whitespace-pre-line text-sm leading-7 text-slate-600">{product.description||"Deskripsi tambahan belum tersedia."}</p>
     <dl className="mt-6 grid grid-cols-2 gap-3"><div className="rounded-xl border p-4"><dt className="text-xs text-slate-500">SKU</dt><dd className="mt-1 break-all font-bold">{product.sku}</dd></div><div className="rounded-xl border p-4"><dt className="text-xs text-slate-500">Isi kemasan</dt><dd className="mt-1 font-bold">{product.package_quantity} unit</dd></div><div className="rounded-xl border p-4"><dt className="text-xs text-slate-500">Garansi</dt><dd className="mt-1 font-bold">{product.warranty_days>0?product.warranty_days+" hari":"Garansi belum dicantumkan"}</dd></div><div className="rounded-xl border p-4"><dt className="text-xs text-slate-500">Publikasi</dt><dd className="mt-1 font-bold">{product.published_at?new Date(product.published_at).toLocaleDateString("id-ID"):"Tanggal belum tersedia"}</dd></div></dl>
    </section>
    <aside className="space-y-5">
     <section className="rounded-3xl border border-[var(--color-border)] bg-white p-5 sm:p-7"><p className="text-sm font-semibold text-slate-500">Harga produk</p><p className="mt-2 text-3xl font-extrabold">{money(product.retail_price)}</p><p className="mt-3 text-sm leading-6 text-slate-500">Ketersediaan, ongkir, dan harga akhir akan divalidasi ulang oleh server saat checkout. Stok tidak dijanjikan dari halaman katalog.</p><Link href={"/cart?add="+encodeURIComponent(product.id)} className="mt-5 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 py-3 font-extrabold text-white"><ShoppingCart size={18}/> Tambah ke keranjang</Link></section>
     <section className="rounded-3xl border border-[var(--color-border)] bg-white p-5 sm:p-7"><div className="flex items-center gap-2"><ShieldCheck className="text-emerald-700" size={21}/><h2 className="font-extrabold">Kecocokan kendaraan</h2></div><p className="mt-2 text-sm leading-6 text-slate-500">Hanya kecocokan yang berstatus terverifikasi dari sistem yang ditampilkan di bawah ini.</p>
      {fitments.length===0?<div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4"><p className="font-bold text-amber-900">Belum ada fitment terverifikasi</p><p className="mt-1 text-sm text-amber-800">Jangan menganggap produk ini cocok sebelum merek, model, tahun, dan varian kendaraan dikonfirmasi.</p></div>:<div className="mt-4 space-y-3">{fitments.map(f=><article key={f.id} className="rounded-xl border p-4"><div className="flex items-start gap-2"><CheckCircle2 size={18} className="mt-0.5 shrink-0 text-emerald-700"/><div><p className="font-bold">{f.vehicle_variants.vehicle_models.vehicle_makes.name} {f.vehicle_variants.vehicle_models.name}</p><p className="mt-1 text-sm">{f.vehicle_variants.name} · {f.vehicle_variants.year_start??"?"}–{f.vehicle_variants.year_end??"?"}{f.vehicle_variants.engine_code?" · "+f.vehicle_variants.engine_code:""}</p><p className="mt-2 text-xs text-slate-500">{f.evidence_note||"Bukti verifikasi tersimpan."}{f.verified_at?" · Diverifikasi "+new Date(f.verified_at).toLocaleDateString("id-ID"):""}</p>{f.evidence_url&&<a className="mt-2 inline-block text-xs font-bold text-[var(--color-primary)] underline" href={f.evidence_url} target="_blank" rel="noreferrer">Lihat bukti fitment</a>}</div></div></article>)}</div>}
     </section>
     <p className="flex items-start gap-2 px-1 text-xs leading-5 text-slate-500"><PackageCheck size={16} className="mt-0.5 shrink-0"/> Informasi produk berasal dari katalog yang dipublikasikan. Harga dan ketersediaan dikonfirmasi saat pemesanan.</p>
    </aside>
   </div>}
  </div>
 </main>;
}
