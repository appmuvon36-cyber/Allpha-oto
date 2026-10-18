"use client";
import Link from "next/link";

import { useEffect, useState } from "react";
import { ArrowRight, CarFront, Search, ShieldCheck, Wrench, Bike, PackageSearch, CircleHelp } from "lucide-react";
import { PwaInstallPrompt } from "./pwa-client";

type Product = { id: string; name: string; sku: string; brand: string | null; part_number: string | null; category: string; condition: string; retail_price: number | null; status: string };
type Make = {id:string;name:string}; type Model = {id:string;make_id:string;name:string}; type Variant = {id:string;model_id:string;name:string;year_start:number|null;year_end:number|null;engine_code:string|null};
const API = "https://otoclinic-api-production.up.railway.app";

const conditionLabels: Record<string,string> = {
  new_oem: "Baru · OEM", new_aftermarket: "Baru · Aftermarket", used: "Bekas / copotan",
  refurbished: "Rekondisi", remanufactured: "Remanufaktur", damaged_for_parts: "Untuk kanibal part"
};

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [makes,setMakes]=useState<Make[]>([]); const [models,setModels]=useState<Model[]>([]); const [variants,setVariants]=useState<Variant[]>([]);
  const [makeId,setMakeId]=useState(""); const [modelId,setModelId]=useState(""); const [variantId,setVariantId]=useState(""); const [vehicleError,setVehicleError]=useState("");

  useEffect(() => {
    let active=true;
    fetch(API+"/v1/vehicles/makes").then(r=>{if(!r.ok)throw new Error();return r.json()}).then(d=>{if(active)setMakes(d.items??[])}).catch(()=>{if(active)setVehicleError("Merek kendaraan belum dapat dimuat.")});
    return ()=>{active=false};
  },[]);
  useEffect(() => {
    let active=true;setModelId("");setVariantId("");setVariants([]);
    if(!makeId){setModels([]);return ()=>{active=false};}
    fetch(API+"/v1/vehicles/models?make_id="+encodeURIComponent(makeId)).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(d=>{if(active)setModels(d.items??[])}).catch(()=>{if(active)setVehicleError("Model kendaraan belum dapat dimuat.")});
    return ()=>{active=false};
  },[makeId]);
  useEffect(() => {
    let active=true;setVariantId("");
    if(!modelId){setVariants([]);return ()=>{active=false};}
    fetch(API+"/v1/vehicles/variants?model_id="+encodeURIComponent(modelId)).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(d=>{if(active)setVariants(d.items??[])}).catch(()=>{if(active)setVehicleError("Varian kendaraan belum dapat dimuat.")});
    return ()=>{active=false};
  },[modelId]);
  useEffect(() => {
    let active=true;setLoading(true);setError("");
    const params=new URLSearchParams({limit:"24"}); if(query.trim())params.set("q",query.trim()); if(variantId)params.set("variant_id",variantId);
    fetch(API+"/v1/catalog/products?"+params.toString()).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(d=>{if(active)setProducts((d.items??[]) as Product[])}).catch(()=>{if(active){setProducts([]);setError("Katalog belum dapat dimuat. Silakan coba kembali.")}}).finally(()=>{if(active)setLoading(false)});
    return ()=>{active=false};
  },[query,variantId]);
  const filtered=products;
  const money = (n: number | null) => n === null ? "Hubungi untuk harga" : new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(n);

  return <main className="min-h-screen">
    <header className="sticky top-0 z-20 border-b border-[var(--color-border)] bg-white/95 backdrop-blur">
      <div className="mx-auto flex min-h-[72px] max-w-7xl items-center justify-between gap-2 px-3 sm:h-[72px] sm:gap-4 sm:px-6">
        <Link href="/" className="flex min-w-0 items-center gap-2 sm:gap-3" aria-label="OtoClinic beranda">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-primary)] text-white"><Wrench size={22}/></span>
          <span><strong className="block text-lg font-extrabold tracking-tight">OtoClinic</strong><span className="block text-[9px] font-semibold uppercase tracking-[.1em] text-slate-500 sm:text-[10px] sm:tracking-[.15em]">Spare part otomotif</span></span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm font-semibold text-slate-600 md:flex"><a href="#katalog" className="hover:text-[var(--color-primary)]">Katalog</a><a href="#cara-kerja" className="hover:text-[var(--color-primary)]">Cara kerja</a><a href="#bantuan" className="hover:text-[var(--color-primary)]">Bantuan</a></nav>
        <div className="flex shrink-0 items-center gap-2"><PwaInstallPrompt/><a href="#katalog" className="hidden rounded-xl bg-[var(--color-primary)] px-3 py-2.5 text-xs font-bold text-white sm:inline-flex sm:px-4 sm:text-sm">Cari spare part</a></div>
      </div>
    </header>
    <section className="relative overflow-hidden bg-[var(--color-ink)] text-white">
      <div className="mx-auto grid max-w-7xl items-center gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[1.2fr_.8fr] lg:py-24">
        <div><span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold text-orange-200"><ShieldCheck size={14}/> Informasi lebih jelas, pilihan lebih tepat</span>
          <h1 className="mt-6 max-w-2xl text-4xl font-extrabold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">Spare part tepat. <span className="text-orange-300">Kendaraan tetap jalan.</span></h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">Cari suku cadang mobil dan motor dengan informasi kondisi, kecocokan kendaraan, serta garansi yang transparan.</p>
          <form onSubmit={e=>{e.preventDefault();document.getElementById("katalog")?.scrollIntoView({behavior:"smooth"});}} className="mt-8 flex max-w-2xl gap-2 rounded-2xl bg-white p-2 shadow-xl shadow-black/10"><Search className="ml-2 mt-3 shrink-0 text-slate-400" size={21}/><input aria-label="Cari nama spare part atau nomor part" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Nama spare part, merek, atau nomor part..." className="min-w-0 flex-1 bg-transparent px-1 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 sm:text-base"/><button className="rounded-xl bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white sm:px-6">Cari</button></form>
          <p className="mt-3 text-xs text-slate-400">Pastikan tipe dan tahun kendaraan sebelum membeli.</p><div className="mt-4 grid max-w-2xl grid-cols-1 gap-2 sm:grid-cols-3"><select aria-label="Merek kendaraan" value={makeId} onChange={e=>setMakeId(e.target.value)} className="min-h-11 min-w-0 rounded-xl border border-white/15 bg-white/10 px-3 text-sm text-white"><option value="" className="text-slate-900">Semua merek</option>{makes.map(m=><option className="text-slate-900" key={m.id} value={m.id}>{m.name}</option>)}</select><select aria-label="Model kendaraan" value={modelId} onChange={e=>setModelId(e.target.value)} disabled={!makeId||models.length===0} className="min-h-11 min-w-0 rounded-xl border border-white/15 bg-white/10 px-3 text-sm text-white disabled:opacity-50"><option value="" className="text-slate-900">Semua model</option>{models.map(m=><option className="text-slate-900" key={m.id} value={m.id}>{m.name}</option>)}</select><select aria-label="Varian/tahun kendaraan" value={variantId} onChange={e=>setVariantId(e.target.value)} disabled={!modelId||variants.length===0} className="min-h-11 min-w-0 rounded-xl border border-white/15 bg-white/10 px-3 text-sm text-white disabled:opacity-50"><option value="" className="text-slate-900">Semua varian/tahun</option>{variants.map(v=><option className="text-slate-900" key={v.id} value={v.id}>{v.name} {v.year_start||v.year_end?("· "+(v.year_start??"?")+"–"+(v.year_end??"?")):""} {v.engine_code?("· "+v.engine_code):""}</option>)}</select></div>{vehicleError&&<p role="status" className="mt-2 text-xs text-orange-200">{vehicleError}</p>}{variantId&&<button type="button" onClick={()=>setVariantId("")} className="mt-2 text-xs font-bold text-orange-200 underline">Hapus filter kendaraan</button>}
        </div>
        <div className="grid grid-cols-1 items-stretch gap-4 sm:grid-cols-2"><div className="flex h-full flex-col rounded-3xl border border-white/10 bg-white/[.06] p-5 sm:p-7"><CarFront size={30} className="text-orange-300"/><h2 className="mt-5 text-lg font-bold sm:text-xl">Spare part mobil</h2><p className="mt-2 text-sm leading-6 text-slate-300">OEM, aftermarket, bekas, dan rekondisi.</p></div><div className="flex h-full flex-col rounded-3xl border border-white/10 bg-white/[.06] p-5 sm:p-7"><Bike size={30} className="text-orange-300"/><h2 className="mt-5 text-lg font-bold sm:text-xl">Spare part motor</h2><p className="mt-2 text-sm leading-6 text-slate-300">Pilihan part sesuai kendaraan dan kebutuhan.</p></div><div className="flex items-start gap-4 rounded-2xl border border-white/10 bg-white/[.06] p-5 sm:col-span-2 sm:p-6"><ShieldCheck className="mt-1 shrink-0 text-emerald-300" size={24}/><div><p className="font-bold">Fitment dan kondisi harus jelas</p><p className="mt-1 text-sm text-slate-300">Status kecocokan ditampilkan berdasarkan bukti yang tersedia, bukan asumsi.</p></div></div></div>
      </div>
    </section>
    <section id="katalog" className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-extrabold uppercase tracking-[.18em] text-[var(--color-primary)]">Katalog</p><h2 className="mt-2 text-2xl font-extrabold tracking-tight sm:text-3xl">Spare part pilihan</h2><p className="mt-2 text-sm text-slate-500">Produk yang ditampilkan berasal dari katalog publik OtoClinic.</p></div><span className="text-xs text-slate-500">Harga dan stok perlu dikonfirmasi sebelum checkout.</span></div>
      {loading ? <div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{[1,2,3,4].map(i=><div key={i} className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white p-5"><div className="h-4 w-2/3 rounded bg-slate-100"/><div className="mt-4 h-3 w-1/2 rounded bg-slate-100"/><div className="mt-12 h-5 w-1/3 rounded bg-slate-100"/></div>)}</div>
      : error ? <div role="alert" className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">{error}</div>
     
      : filtered.length===0 ? <div className="mt-7 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><PackageSearch className="mx-auto text-slate-400" size={32}/><h3 className="mt-3 font-bold">{query ? "Produk tidak ditemukan" : "Belum ada produk yang dipublikasikan"}</h3><p className="mt-2 text-sm text-slate-500">{query ? "Coba nama atau nomor part yang berbeda." : "Produk akan tampil setelah katalog nyata melewati proses review dan publikasi."}</p></div>
      : <div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{filtered.map(p=><article key={p.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:shadow-md"><div className="flex h-24 items-center justify-center rounded-xl bg-slate-50"><Wrench size={30} className="text-slate-300"/></div><p className="mt-4 text-[11px] font-bold uppercase tracking-wide text-slate-500">{p.category}</p><h3 className="mt-1 font-bold leading-5">{p.name}</h3><p className="mt-2 text-xs text-slate-500">{p.brand || "Merek belum dicantumkan"}{p.part_number ? " · "+p.part_number : ""}</p><span className="mt-3 w-fit rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{conditionLabels[p.condition] || p.condition}</span><div className="mt-auto pt-5"><p className="text-base font-extrabold">{money(p.retail_price)}</p><p className="mt-1 text-[11px] text-slate-400">Fitment dan stok dikonfirmasi saat pemesanan</p></div></article>)}</div>}
    </section>
    <section id="cara-kerja" className="border-y border-slate-200 bg-white"><div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-14"><h2 className="text-2xl font-extrabold">Belanja dengan informasi yang jelas</h2><div className="mt-6 grid gap-4 md:grid-cols-3">{[["01","Pilih kendaraan","Cocokkan merek, model, tahun, dan varian."],["02","Periksa kondisi","Bedakan barang baru, copotan, rekondisi, dan lainnya."],["03","Konfirmasi pesanan","Pastikan harga, ketersediaan, garansi, dan fitment sebelum pembayaran."]].map(s=><div key={s[0]} className="rounded-2xl border border-slate-200 p-5"><span className="text-sm font-extrabold text-[var(--color-primary)]">{s[0]}</span><h3 className="mt-3 font-bold">{s[1]}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{s[2]}</p></div>)}</div></div></section>
    <footer id="bantuan" className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6"><div><p className="font-extrabold text-slate-800">OtoClinic</p><p className="mt-1">Marketplace spare part otomotif Indonesia.</p></div><p className="flex items-center gap-2"><CircleHelp size={15}/> Selalu konfirmasi fitment, harga, stok, dan garansi sebelum transaksi.</p><div className="flex flex-wrap items-center gap-4"><a href="#katalog" className="flex items-center gap-1 font-bold text-[var(--color-primary)]">Jelajahi katalog <ArrowRight size={14}/></a><Link href="/supplier" className="font-bold text-slate-600 underline underline-offset-4">Portal mitra supplier</Link></div></footer>
  <nav className="mobile-bottom-nav" aria-label="Navigasi utama"><Link href="/" aria-current="page"><span>⌂</span><small>Beranda</small></Link><a href="#katalog"><span>⌕</span><small>Katalog</small></a><a href="#permintaan"><span>＋</span><small>Request</small></a><a href="#favorit"><span>♡</span><small>Favorit</small></a><a href="#akun"><span>♙</span><small>Akun</small></a></nav><section id="permintaan" className="mx-4 mb-6 rounded-2xl border border-orange-200 bg-orange-50 p-4"><strong className="text-sm">Tidak menemukan spare part?</strong><p className="mt-1 text-xs leading-5 text-slate-600">Ajukan permintaan agar tim sourcing membantu mencarikan part yang sesuai.</p><a className="mt-3 inline-flex rounded-lg bg-[var(--color-primary)] px-3 py-2 text-xs font-bold text-white" href="mailto:sourcing@otoclinic.id?subject=Permintaan%20Spare%20Part">Ajukan permintaan</a></section>
  </main>;
}
