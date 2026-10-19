"use client";
import Link from "next/link";

import { useEffect, useState } from "react";
import { ArrowRight, CarFront, Search, ShieldCheck, Wrench, Bike, PackageSearch, CircleHelp, ShoppingCart } from "lucide-react";
import { PwaInstallPrompt } from "./pwa-client";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type Product = { id: string; name: string; sku: string; brand: string | null; part_number: string | null; category: string; condition: string; retail_price: number | null; status: string; image_url?: string | null; images?: {id:string;url:string;alt_text:string;media_kind:string;is_primary:boolean}[] };
type Make = {id:string;name:string}; type Model = {id:string;make_id:string;name:string}; type Variant = {id:string;model_id:string;name:string;year_start:number|null;year_end:number|null;engine_code:string|null};
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";

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
  const [cartBusy,setCartBusy]=useState("");
  const [cartNotice,setCartNotice]=useState("");

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
  async function addToCart(productId:string){
    setCartBusy(productId);setCartNotice("");
    try{
      const supabase=getSupabaseBrowserClient();
      if(!supabase){setCartNotice("Autentikasi belum dikonfigurasi.");return;}
      const {data:{session}}=await supabase.auth.getSession();
      if(!session){window.location.assign("/cart?add="+encodeURIComponent(productId));return;}
      const response=await fetch(API+"/v1/cart/mutations",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+session.access_token,"Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({action:"cart_add",product_id:productId,quantity:1})});
      const body=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(body.detail??"Produk tidak dapat ditambahkan.");
      setCartNotice("Produk berhasil ditambahkan ke keranjang.");
    }catch(e){setCartNotice(e instanceof Error?e.message:"Keranjang tidak dapat diperbarui.");}
    finally{setCartBusy("");}
  }
  const filtered=products;
  const money = (n: number | null) => n === null ? "Hubungi untuk harga" : new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(n);

  return <main className="min-h-screen">
    <header className="sticky top-0 z-20 border-b border-[var(--color-border)] bg-white/95 backdrop-blur">
      <div className="mx-auto flex min-h-[72px] max-w-7xl items-center justify-between gap-2 px-3 sm:h-[72px] sm:gap-4 sm:px-6">
        <Link href="/" className="flex min-w-0 items-center gap-2 sm:gap-3" aria-label="OtoClinic beranda">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-primary)] text-white"><Wrench size={22}/></span>
          <span><strong className="block text-lg font-extrabold tracking-tight">OtoClinic</strong><span className="block text-[9px] font-semibold uppercase tracking-[.1em] text-slate-500 sm:text-[10px] sm:tracking-[.15em]">Spare part otomotif</span></span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm font-semibold text-slate-600 md:flex"><a href="#katalog" className="hover:text-[var(--color-primary)]">Katalog</a><a href="#cara-kerja" className="hover:text-[var(--color-primary)]">Cara kerja</a><Link href="/account" className="hover:text-[var(--color-primary)]">Akun & pesanan</Link><a href="#bantuan" className="hover:text-[var(--color-primary)]">Bantuan</a></nav>
        <div className="flex shrink-0 items-center gap-2"><Link href="/cart" className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-2.5 text-xs font-bold text-slate-700 sm:text-sm"><ShoppingCart size={16}/> Keranjang</Link><PwaInstallPrompt/><a href="#katalog" className="hidden rounded-xl bg-[var(--color-primary)] px-3 py-2.5 text-xs font-bold text-white sm:inline-flex sm:px-4 sm:text-sm">Cari spare part</a></div>
      </div>
    </header>
    <section className="mx-auto max-w-7xl px-3 pt-3 sm:px-6 sm:pt-5">
      <div className="store-promo-banner relative isolate overflow-hidden rounded-2xl sm:rounded-3xl" aria-label="Banner informasi dan promosi OtoClinic">
        <div className="store-promo-copy relative z-10 max-w-xl p-5 sm:p-8 lg:p-10">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-white/25 bg-white/10 px-3 py-1 text-[10px] font-extrabold uppercase tracking-[.14em] text-white"><ShieldCheck size={13}/> OtoClinic · Spare part otomotif</span>
          <h1 className="mt-3 max-w-lg text-2xl font-black leading-tight tracking-tight text-white sm:text-4xl">Cari spare part yang tepat untuk kendaraan Anda.</h1>
          <p className="mt-2 max-w-md text-xs leading-5 text-white/85 sm:text-sm sm:leading-6">Telusuri katalog, periksa informasi kecocokan, dan pastikan kondisi barang sebelum memesan.</p>
          <a href="#katalog" className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-xs font-extrabold text-[var(--color-ink)] shadow-sm hover:bg-orange-50 sm:text-sm">Jelajahi katalog <ArrowRight size={15}/></a>
        </div>
        <div className="store-promo-art" aria-hidden="true">
          <div className="promo-orbit promo-orbit-one"></div><div className="promo-orbit promo-orbit-two"></div>
          <div className="promo-part promo-part-disc"><Wrench size={50}/></div>
          <div className="promo-part promo-part-shield"><ShieldCheck size={26}/></div>
          <div className="promo-part promo-part-box"><PackageSearch size={30}/></div>
        </div>
        <span className="absolute bottom-3 right-3 rounded-md bg-black/20 px-2 py-1 text-[9px] font-bold tracking-wide text-white/80">BANNER PROMO</span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 sm:mt-4 sm:gap-3">
        <div className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white p-2.5 sm:gap-3 sm:p-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-orange-50 text-[var(--color-primary)]"><CarFront size={19}/></span><span className="min-w-0"><strong className="block text-[10px] leading-4 sm:text-xs">Cari part</strong><small className="block text-[9px] leading-3 text-slate-500 sm:text-[10px]">Mobil & motor</small></span></div>
        <div className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white p-2.5 sm:gap-3 sm:p-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-emerald-50 text-emerald-700"><ShieldCheck size={19}/></span><span className="min-w-0"><strong className="block text-[10px] leading-4 sm:text-xs">Cek kecocokan</strong><small className="block text-[9px] leading-3 text-slate-500 sm:text-[10px]">Lihat bukti</small></span></div>
        <div className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white p-2.5 sm:gap-3 sm:p-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue-700"><PackageSearch size={19}/></span><span className="min-w-0"><strong className="block text-[10px] leading-4 sm:text-xs">Request part</strong><small className="block text-[9px] leading-3 text-slate-500 sm:text-[10px]">Jika belum ada</small></span></div>
      </div>
      <form onSubmit={e=>{e.preventDefault();document.getElementById("katalog")?.scrollIntoView({behavior:"smooth"});}} className="store-search mt-4 flex min-h-12 items-center gap-2 rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm sm:mt-5 sm:min-h-14 sm:rounded-2xl sm:p-2">
        <Search className="ml-2 shrink-0 text-slate-400" size={19}/>
        <input aria-label="Cari nama spare part atau nomor part" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Cari nama, merek, SKU atau nomor part..." className="min-w-0 flex-1 bg-transparent px-1 py-2 text-xs outline-none placeholder:text-slate-400 sm:text-sm"/>
        <button className="min-h-10 rounded-lg bg-[var(--color-primary)] px-4 text-xs font-extrabold text-white sm:min-h-11 sm:rounded-xl sm:px-5 sm:text-sm">Cari</button>
      </form>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <label className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2"><CarFront size={16} className="shrink-0 text-slate-400"/><select aria-label="Merek kendaraan" value={makeId} onChange={e=>setMakeId(e.target.value)} className="min-h-8 min-w-0 flex-1 bg-transparent text-xs outline-none"><option value="">Pilih merek kendaraan</option>{makes.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2"><CarFront size={16} className="shrink-0 text-slate-400"/><select aria-label="Model kendaraan" value={modelId} onChange={e=>setModelId(e.target.value)} disabled={!makeId||models.length===0} className="min-h-8 min-w-0 flex-1 bg-transparent text-xs outline-none disabled:text-slate-400"><option value="">Pilih model</option>{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2"><CarFront size={16} className="shrink-0 text-slate-400"/><select aria-label="Varian dan tahun kendaraan" value={variantId} onChange={e=>setVariantId(e.target.value)} disabled={!modelId||variants.length===0} className="min-h-8 min-w-0 flex-1 bg-transparent text-xs outline-none disabled:text-slate-400"><option value="">Pilih varian / tahun</option>{variants.map(v=><option key={v.id} value={v.id}>{v.name} {v.year_start||v.year_end?("· "+(v.year_start??"?")+"–"+(v.year_end??"?")):""} {v.engine_code?("· "+v.engine_code):""}</option>)}</select></label>
      </div>
      {vehicleError&&<p role="status" className="mt-2 text-xs text-amber-700">{vehicleError}</p>}
      {variantId&&<button type="button" onClick={()=>setVariantId("")} className="mt-2 text-xs font-bold text-[var(--color-primary)] underline">Hapus filter kendaraan</button>}
    </section>
    <section id="kategori" className="mx-auto max-w-7xl px-4 pt-7 sm:px-6 sm:pt-10">
      <div className="flex items-end justify-between gap-3"><div><p className="text-[11px] font-extrabold uppercase tracking-[.16em] text-[var(--color-primary)]">Belanja lebih cepat</p><h2 className="mt-1 text-xl font-extrabold tracking-tight sm:text-2xl">Cari berdasarkan kategori</h2></div><span className="hidden text-xs text-slate-500 sm:block">Pilih kategori untuk mencari katalog</span></div>
      <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6 sm:gap-3">{[{label:"Mesin",term:"mesin",icon:"⚙"},{label:"Kaki-kaki",term:"kaki-kaki",icon:"◉"},{label:"Kelistrikan",term:"kelistrikan",icon:"ϟ"},{label:"Body",term:"body",icon:"▧"},{label:"Sistem rem",term:"rem",icon:"◈"},{label:"Oli & filter",term:"filter",icon:"▤"}].map(item=><button key={item.label} type="button" onClick={()=>{setQuery(item.term);document.getElementById("katalog")?.scrollIntoView({behavior:"smooth"});}} className="flex min-h-[94px] flex-col items-start justify-center rounded-2xl border border-slate-200 bg-white p-3 text-left transition hover:border-orange-200 hover:bg-orange-50/50 sm:min-h-[112px] sm:p-4"><span aria-hidden="true" className="grid h-9 w-9 place-items-center rounded-xl bg-orange-50 text-lg text-[var(--color-primary)] sm:h-11 sm:w-11 sm:text-xl">{item.icon}</span><span className="mt-2 text-xs font-extrabold sm:text-sm">{item.label}</span></button>)}</div>
    </section>
    <section className="mx-auto max-w-7xl px-3 pt-7 sm:px-6 sm:pt-10" aria-labelledby="koleksi-title">
      <div className="flex items-end justify-between gap-3"><div><p className="text-[10px] font-extrabold uppercase tracking-[.16em] text-[var(--color-primary)]">Temukan kebutuhan Anda</p><h2 id="koleksi-title" className="mt-1 text-lg font-black tracking-tight sm:text-2xl">Jelajahi koleksi</h2></div><a href="#katalog" className="text-[11px] font-extrabold text-[var(--color-primary)] sm:text-xs">Lihat semua</a></div>
      <div className="collection-rail mt-3 flex gap-2 overflow-x-auto pb-2" aria-label="Kategori koleksi katalog">
        {[["Semua produk","katalog"],["Best seller","koleksi-best-seller"],["Popular","koleksi-popular"],["Secondary","koleksi-secondary"],["Produk baru","koleksi-new"],["Promo","koleksi-promo"],["Iklan","koleksi-ads"]].map(([label,id],i)=><a key={id} href={"#"+id} className={`shrink-0 rounded-full border px-4 py-2.5 text-xs font-extrabold ${i===0?"border-[var(--color-primary)] bg-[var(--color-primary)] text-white":"border-slate-200 bg-white text-slate-700 hover:border-orange-200 hover:text-[var(--color-primary)]"}`}>{label}</a>)}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3">
        {[["koleksi-best-seller","Best Seller","Produk dengan penjualan terverifikasi."],["koleksi-popular","Popular","Produk dengan minat pencarian terukur."],["koleksi-secondary","Secondary","Pilihan part pendukung dan alternatif."],["koleksi-new","Produk Baru","Produk yang baru dipublikasikan."],["koleksi-promo","Promo","Penawaran dengan periode dan syarat yang jelas."],["koleksi-ads","Iklan & Sponsor","Slot promosi yang dikelola secara resmi."]].map(([id,title,description],i)=><a key={id} id={id} href="#katalog" className="collection-tile flex min-h-[94px] min-w-0 flex-col justify-between rounded-xl border border-slate-200 bg-white p-3 sm:min-h-[112px] sm:rounded-2xl sm:p-4"><span className={`grid h-8 w-8 place-items-center rounded-lg ${i===4||i===5?"bg-orange-50 text-[var(--color-primary)]":"bg-slate-100 text-slate-700"}`}>{[<PackageSearch size={17}/>,<Search size={17}/>,<Wrench size={17}/>,<ArrowRight size={17}/>,<ShieldCheck size={17}/>,<CircleHelp size={17}/>][i]}</span><span><strong className="block text-xs font-extrabold sm:text-sm">{title}</strong><small className="mt-1 block text-[10px] leading-4 text-slate-500">{description}</small></span></a>)}
      </div>
      <p className="mt-2 text-[10px] leading-4 text-slate-500">Label Best Seller, Popular, Promo, dan Iklan hanya akan menampilkan produk setelah data kurasi/penjualan/promosi tersedia. Tidak ada diskon atau statistik yang dibuat-buat.</p>
    </section>
    <section id="katalog" className="mx-auto max-w-7xl px-4 py-7 sm:px-6 sm:py-10">
      <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end"><div><p className="text-[10px] font-extrabold uppercase tracking-[.16em] text-[var(--color-primary)]">Katalog terverifikasi</p><h2 className="mt-1 text-xl font-black tracking-tight sm:text-2xl">Semua produk</h2><p className="mt-1 text-xs text-slate-500 sm:text-sm">Data live dari katalog publik OtoClinic. Tidak ada produk contoh.</p></div><span className="text-[10px] text-slate-500 sm:text-xs">Harga, stok, dan kecocokan perlu dikonfirmasi.</span></div>
      {loading ? <div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{[1,2,3,4].map(i=><div key={i} className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white p-5"><div className="h-4 w-2/3 rounded bg-slate-100"/><div className="mt-4 h-3 w-1/2 rounded bg-slate-100"/><div className="mt-12 h-5 w-1/3 rounded bg-slate-100"/></div>)}</div>
      : error ? <div role="alert" className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">{error}</div>
     
      : filtered.length===0 ? <div className="mt-7 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><PackageSearch className="mx-auto text-slate-400" size={32}/><h3 className="mt-3 font-bold">{query ? "Produk tidak ditemukan" : "Belum ada produk yang dipublikasikan"}</h3><p className="mt-2 text-sm text-slate-500">{query ? "Coba nama atau nomor part yang berbeda." : "Produk akan tampil setelah katalog nyata melewati proses review dan publikasi."}</p></div>
      : <>{cartNotice&&<p role="status" className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{cartNotice}</p>}<div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{filtered.map(p=><article key={p.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:shadow-md"><div className="flex h-40 items-center justify-center overflow-hidden rounded-xl bg-slate-50">{p.image_url ? <img src={p.image_url} alt={p.images?.find(image=>image.is_primary)?.alt_text || ("Foto produk " + p.name)} loading="lazy" className="h-full w-full object-contain" /> : <div className="flex flex-col items-center gap-2 text-slate-400"><Wrench size={30} className="text-slate-300"/><span className="text-[11px]">Foto belum tersedia</span></div>}</div><p className="mt-4 text-[11px] font-bold uppercase tracking-wide text-slate-500">{p.category}</p><h3 className="mt-1 font-bold leading-5"><Link href={"/products/"+p.id} className="hover:text-[var(--color-primary)] focus-visible:underline">{p.name}</Link></h3><p className="mt-2 text-xs text-slate-500">{p.brand || "Merek belum dicantumkan"}{p.part_number ? " · "+p.part_number : ""}</p><Link href={"/products/"+p.id} className="mt-2 inline-flex text-xs font-bold text-[var(--color-primary)] underline">Detail produk</Link><span className="mt-3 w-fit rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{conditionLabels[p.condition] || p.condition}</span><div className="mt-auto pt-5"><p className="text-base font-extrabold">{money(p.retail_price)}</p><p className="mt-1 text-[11px] text-slate-400">Fitment dan stok dikonfirmasi saat pemesanan</p><button disabled={cartBusy===p.id} onClick={()=>void addToCart(p.id)} className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-3 py-2.5 text-sm font-bold text-white disabled:opacity-50">{cartBusy===p.id?"Memproses…":<><ShoppingCart size={15}/> Tambah ke keranjang</>}</button></div></article>)}</div></>}
    </section>
    <section id="cara-kerja" className="border-y border-slate-200 bg-white"><div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-14"><h2 className="text-2xl font-extrabold">Belanja dengan informasi yang jelas</h2><div className="mt-6 grid gap-4 md:grid-cols-3">{[["01","Pilih kendaraan","Cocokkan merek, model, tahun, dan varian."],["02","Periksa kondisi","Bedakan barang baru, copotan, rekondisi, dan lainnya."],["03","Konfirmasi pesanan","Pastikan harga, ketersediaan, garansi, dan fitment sebelum pembayaran."]].map(s=><div key={s[0]} className="rounded-2xl border border-slate-200 p-5"><span className="text-sm font-extrabold text-[var(--color-primary)]">{s[0]}</span><h3 className="mt-3 font-bold">{s[1]}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{s[2]}</p></div>)}</div></div></section>
    <footer id="bantuan" className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6"><div><p className="font-extrabold text-slate-800">OtoClinic</p><p className="mt-1">Marketplace spare part otomotif Indonesia.</p></div><p className="flex items-center gap-2"><CircleHelp size={15}/> Selalu konfirmasi fitment, harga, stok, dan garansi sebelum transaksi.</p><div className="flex flex-wrap items-center gap-4"><a href="#katalog" className="flex items-center gap-1 font-bold text-[var(--color-primary)]">Jelajahi katalog <ArrowRight size={14}/></a><Link href="/supplier" className="font-bold text-slate-600 underline underline-offset-4">Portal mitra supplier</Link></div></footer>
  <nav className="mobile-bottom-nav" aria-label="Navigasi utama"><Link href="/" aria-current="page"><span>⌂</span><small>Beranda</small></Link><a href="#kategori"><span>▦</span><small>Kategori</small></a><a href="#permintaan"><span>＋</span><small>Request</small></a><a href="#favorit"><span>♡</span><small>Favorit</small></a><a href="#akun"><span>♙</span><small>Akun</small></a></nav><section id="permintaan" className="mx-4 mb-6 rounded-2xl border border-orange-200 bg-orange-50 p-4"><strong className="text-sm">Tidak menemukan spare part?</strong><p className="mt-1 text-xs leading-5 text-slate-600">Ajukan permintaan agar tim sourcing membantu mencarikan part yang sesuai.</p><a className="mt-3 inline-flex rounded-lg bg-[var(--color-primary)] px-3 py-2 text-xs font-bold text-white" href="mailto:sourcing@otoclinic.id?subject=Permintaan%20Spare%20Part">Ajukan permintaan</a></section>
  </main>;
}
