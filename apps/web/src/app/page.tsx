"use client";
import Link from "next/link";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, CarFront, Search, ShieldCheck, Wrench, PackageSearch, CircleHelp, ShoppingCart, House, Grid2X2, Plus, Heart, UserRound } from "lucide-react";
import { PwaInstallPrompt } from "./pwa-client";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type Product = { id: string; name: string; sku: string; brand: string | null; part_number: string | null; category: string; condition: string; retail_price: number | null; status: string; published_at?: string | null; image_url?: string | null; stock_status?: "in_stock"|"low_stock"|"out_of_stock"|"stale"|"unverified"; stock_checked_at?: string|null; images?: {id:string;url:string;alt_text:string;media_kind:string;is_primary:boolean}[] };
type Category = {id:string;parent_id:string|null;name:string;slug:string;code:string;vehicle_scope:string;sort_order:number}; type Make = {id:string;name:string}; type Model = {id:string;make_id:string;name:string}; type Variant = {id:string;model_id:string;name:string;year_start:number|null;year_end:number|null;engine_code:string|null};
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";

const conditionLabels: Record<string,string> = {
  new_oem: "Baru · OEM", new_aftermarket: "Baru · Aftermarket", used: "Bekas / copotan",
  refurbished: "Rekondisi", remanufactured: "Remanufaktur", damaged_for_parts: "Untuk kanibal part"
};

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [selectedCategory,setSelectedCategory]=useState("");
  const [partNumber,setPartNumber]=useState("");
  const [condition,setCondition]=useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [categories,setCategories]=useState<Category[]>([]);
  const [categoryError,setCategoryError]=useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [makes,setMakes]=useState<Make[]>([]); const [models,setModels]=useState<Model[]>([]); const [variants,setVariants]=useState<Variant[]>([]);
  const [makeId,setMakeId]=useState(""); const [modelId,setModelId]=useState(""); const [variantId,setVariantId]=useState(""); const [vehicleError,setVehicleError]=useState("");
  const [cartBusy,setCartBusy]=useState("");
  const [cartNotice,setCartNotice]=useState("");
  const [requestPartName,setRequestPartName]=useState("");
  const [requestPartNumber,setRequestPartNumber]=useState("");
  const [requestMake,setRequestMake]=useState("");
  const [requestModel,setRequestModel]=useState("");
  const [requestYear,setRequestYear]=useState("");
  const [requestQuantity,setRequestQuantity]=useState("1");
  const [requestDetails,setRequestDetails]=useState("");
  const [requestPhone,setRequestPhone]=useState("");
  const [requestBusy,setRequestBusy]=useState(false);
  const [requestNotice,setRequestNotice]=useState<{kind:"success"|"error";text:string}|null>(null);
  const requestKey=useRef("");
  const selectedCategoryItem=categories.find(item=>item.id===selectedCategory);
  const selectedCategoryChildren=categories.filter(item=>item.parent_id===selectedCategory);

  useEffect(() => {
    let active=true;
    fetch(API+"/v1/catalog/categories").then(r=>{if(!r.ok)throw new Error();return r.json()}).then(d=>{if(active){setCategories(d.items??[]);setCategoryError("");}}).catch(()=>{if(active){setCategories([]);setCategoryError("Kategori belum dapat dimuat dari master katalog.");}});
    return ()=>{active=false};
  },[]);

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
    const params=new URLSearchParams({limit:"24"}); if(query.trim())params.set("q",query.trim()); if(partNumber.trim())params.set("part_number",partNumber.trim()); if(selectedCategory)params.set("category_id",selectedCategory); if(condition)params.set("condition",condition); if(variantId)params.set("variant_id",variantId);
    fetch(API+"/v1/catalog/products?"+params.toString()).then(r=>{if(!r.ok)throw new Error();return r.json()}).then(d=>{if(active)setProducts((d.items??[]) as Product[])}).catch(()=>{if(active){setProducts([]);setError("Katalog belum dapat dimuat. Silakan coba kembali.")}}).finally(()=>{if(active)setLoading(false)});
    return ()=>{active=false};
  },[query,partNumber,condition,variantId,selectedCategory]);
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
  async function submitSourcingRequest(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setRequestNotice(null);setRequestBusy(true);
    try{
      const supabase=getSupabaseBrowserClient();
      if(!supabase){throw new Error("Layanan autentikasi belum tersedia. Coba lagi nanti.");}
      const {data:{session}}=await supabase.auth.getSession();
      if(!session){window.location.assign("/login?next=%2F%23permintaan");return;}
      if(!requestKey.current)requestKey.current=crypto.randomUUID();
      const response=await fetch(API+"/v1/sourcing/requests",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+session.access_token,"Idempotency-Key":requestKey.current},body:JSON.stringify({part_name:requestPartName.trim(),part_number:requestPartNumber.trim()||null,vehicle_make:requestMake.trim()||null,vehicle_model:requestModel.trim()||null,vehicle_year:requestYear?Number(requestYear):null,quantity:Number(requestQuantity),details:requestDetails.trim()||null,contact_phone:requestPhone.trim()||null})});
      const body=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(body.detail??"Permintaan belum dapat disimpan. Silakan coba lagi.");
      const requestId=body.request?.id;
      setRequestNotice({kind:"success",text:"Permintaan berhasil tersimpan"+(requestId?" dengan referensi "+requestId.slice(0,8).toUpperCase():"")+". Tim sourcing dapat menindaklanjuti setelah antrean operasional tersedia."});
      setRequestPartName("");setRequestPartNumber("");setRequestMake("");setRequestModel("");setRequestYear("");setRequestQuantity("1");setRequestDetails("");setRequestPhone("");requestKey.current="";
    }catch(e){setRequestNotice({kind:"error",text:e instanceof Error?e.message:"Permintaan tidak dapat disimpan."});}
    finally{setRequestBusy(false);}
  }
  const stockLabel=(status:Product["stock_status"])=>status==="in_stock"?"Stok tersedia":status==="low_stock"?"Stok terbatas":status==="out_of_stock"?"Stok habis":status==="stale"?"Stok perlu diperbarui":"Stok belum terverifikasi";
  const stockTone=(status:Product["stock_status"])=>status==="in_stock"?"bg-emerald-50 text-emerald-800":status==="low_stock"?"bg-amber-50 text-amber-800":status==="out_of_stock"?"bg-rose-50 text-rose-800":"bg-slate-100 text-slate-600";
  const filtered=products;
  const recentProducts=products.filter(p=>p.published_at && Number.isFinite(Date.parse(p.published_at)) && Date.parse(p.published_at)>=Date.now()-30*24*60*60*1000);
  const secondaryProducts=products.filter(p=>["used","refurbished","remanufactured","damaged_for_parts"].includes(p.condition));
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
    <section className="mx-auto max-w-7xl px-3 pt-4 sm:px-6 sm:pt-6" aria-label="Hero OtoClinic">
      <div className="relative isolate overflow-hidden rounded-[1.5rem] bg-[var(--color-ink)] px-5 py-7 text-white sm:rounded-[2rem] sm:px-9 sm:py-10 lg:px-12 lg:py-12">
        <div aria-hidden="true" className="pointer-events-none absolute -right-10 -top-12 h-52 w-52 rounded-full border border-white/10 sm:h-72 sm:w-72"></div>
        <div aria-hidden="true" className="pointer-events-none absolute right-8 top-8 hidden h-32 w-32 rounded-full border border-white/10 sm:block"></div>
        <div className="relative grid items-center gap-7 md:grid-cols-[1.15fr_.85fr] md:gap-10">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-[11px] font-bold text-orange-100"><ShieldCheck size={14}/> Katalog spare part dengan informasi yang jelas</span>
            <h2 className="mt-4 max-w-2xl text-3xl font-black leading-[1.12] tracking-tight sm:text-4xl lg:text-5xl">Spare part tepat, kendaraan tetap sehat.</h2>
            <p className="mt-4 max-w-xl text-sm leading-6 text-slate-200 sm:text-base sm:leading-7">Cari berdasarkan nama atau nomor part, cocokkan dengan kendaraan, lalu periksa kondisi, garansi, dan bukti fitment sebelum memesan.</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <a href="#pencarian-sparepart" className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--color-primary)] px-5 py-3 text-sm font-extrabold text-white transition hover:bg-orange-600">Cari spare part <ArrowRight size={17} className="ml-2"/></a>
              <a href="#kategori" className="inline-flex min-h-11 items-center justify-center rounded-xl border border-white/25 bg-white/5 px-5 py-3 text-sm font-bold text-white transition hover:bg-white/10">Jelajahi kategori</a>
            </div>
            <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-xs font-semibold text-slate-200"><span className="inline-flex items-center gap-1.5"><ShieldCheck size={14} className="text-emerald-300"/> Status fitment transparan</span><span className="inline-flex items-center gap-1.5"><PackageSearch size={14} className="text-orange-300"/> Baru dan bekas</span></div>
          </div>
          <div className="relative mx-auto grid w-full max-w-sm grid-cols-2 gap-3 md:max-w-none">
            <div className="flex min-h-32 flex-col justify-between rounded-2xl border border-white/10 bg-white/10 p-4 backdrop-blur-sm sm:min-h-40 sm:p-5"><Wrench size={27} className="text-orange-300"/><div><strong className="block text-sm sm:text-base">Part terarah</strong><span className="mt-1 block text-xs leading-5 text-slate-300">Nama, merek, dan nomor part</span></div></div>
            <div className="mt-6 flex min-h-32 flex-col justify-between rounded-2xl border border-white/10 bg-white/10 p-4 backdrop-blur-sm sm:min-h-40 sm:p-5"><CarFront size={27} className="text-orange-300"/><div><strong className="block text-sm sm:text-base">Cocok kendaraan</strong><span className="mt-1 block text-xs leading-5 text-slate-300">Merek, model, varian, tahun</span></div></div>
            <div className="flex min-h-28 flex-col justify-between rounded-2xl border border-white/10 bg-white/10 p-4 sm:col-span-2 sm:min-h-32 sm:flex-row sm:items-center"><div><strong className="block text-sm sm:text-base">Belanja lebih yakin</strong><span className="mt-1 block text-xs leading-5 text-slate-300">Kondisi dan garansi ditampilkan sesuai data produk.</span></div><span className="mt-3 inline-flex w-fit rounded-lg bg-white/10 px-3 py-2 text-xs font-bold text-orange-100 sm:mt-0">OtoClinic · Spare part otomotif</span></div>
          </div>
        </div>
      </div>
    </section>
    <section id="pencarian-sparepart" className="mx-auto max-w-7xl px-3 pt-4 sm:px-6 sm:pt-6" aria-label="Pencarian dan kendaraan">
      <div className="mb-3 flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2.5 sm:mb-4 sm:px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-orange-50 text-[var(--color-primary)]"><ShieldCheck size={19}/></span>
          <div className="min-w-0"><h1 className="truncate text-xs font-extrabold sm:text-sm">Spare part tepat, kendaraan tetap sehat</h1><p className="text-[10px] text-slate-500 sm:text-xs">Cari, cocokkan, lalu periksa informasi produk.</p></div>
        </div>
        <Link href="/cart" aria-label="Buka keranjang" className="relative grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-slate-200 text-slate-700"><ShoppingCart size={19}/></Link>
      </div>
      <form onSubmit={e=>{e.preventDefault();document.getElementById("katalog")?.scrollIntoView({behavior:"smooth"});}} className="store-search flex min-h-12 items-center gap-2 rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm sm:min-h-14 sm:rounded-2xl sm:p-2">
        <Search className="ml-2 shrink-0 text-slate-400" size={20}/>
        <input aria-label="Cari nama spare part atau nomor part" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Nama spare part, merek, atau nomor part..." className="min-w-0 flex-1 bg-transparent px-1 py-2 text-xs outline-none placeholder:text-slate-400 sm:text-sm"/>
        <button className="min-h-10 rounded-lg bg-[var(--color-primary)] px-4 text-xs font-extrabold text-white sm:min-h-11 sm:rounded-xl sm:px-5 sm:text-sm">Cari</button>
      </form>
      <p className="mt-2 text-[10px] text-slate-500 sm:text-xs">Pastikan tipe dan tahun kendaraan sebelum membeli.</p>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:mt-4 sm:grid-cols-3">
        <label className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5"><CarFront size={17} className="shrink-0 text-slate-500"/><select aria-label="Merek kendaraan" value={makeId} onChange={e=>setMakeId(e.target.value)} className="min-h-8 min-w-0 flex-1 bg-transparent text-xs outline-none"><option value="">Semua merek / pilih kendaraan</option>{makes.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5"><CarFront size={17} className="shrink-0 text-slate-500"/><select aria-label="Model kendaraan" value={modelId} onChange={e=>setModelId(e.target.value)} disabled={!makeId||models.length===0} className="min-h-8 min-w-0 flex-1 bg-transparent text-xs outline-none disabled:text-slate-400"><option value="">Semua model</option>{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5"><CarFront size={17} className="shrink-0 text-slate-500"/><select aria-label="Varian dan tahun kendaraan" value={variantId} onChange={e=>setVariantId(e.target.value)} disabled={!modelId||variants.length===0} className="min-h-8 min-w-0 flex-1 bg-transparent text-xs outline-none disabled:text-slate-400"><option value="">Semua varian / tahun</option>{variants.map(v=><option key={v.id} value={v.id}>{v.name} {v.year_start||v.year_end?("· "+(v.year_start??"?")+"–"+(v.year_end??"?")):""} {v.engine_code?("· "+v.engine_code):""}</option>)}</select></label>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr]">
        <label className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5"><Search size={16} className="shrink-0 text-slate-500"/><input aria-label="Nomor part" value={partNumber} onChange={e=>setPartNumber(e.target.value)} placeholder="Nomor part / kode OEM" className="min-h-8 min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-slate-400 sm:text-sm"/></label>
        <label className="flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5"><PackageSearch size={16} className="shrink-0 text-slate-500"/><select aria-label="Kondisi produk" value={condition} onChange={e=>setCondition(e.target.value)} className="min-h-8 min-w-0 flex-1 bg-transparent text-xs outline-none sm:text-sm"><option value="">Semua kondisi produk</option><option value="new_oem">Baru · OEM</option><option value="new_aftermarket">Baru · Aftermarket</option><option value="used">Bekas / copotan</option><option value="refurbished">Rekondisi</option><option value="remanufactured">Remanufaktur</option><option value="damaged_for_parts">Untuk kanibal part</option></select></label>
      </div>
      {vehicleError&&<p role="status" className="mt-2 text-xs text-amber-700">{vehicleError}</p>}
      {variantId&&<button type="button" onClick={()=>setVariantId("")} className="mt-2 text-xs font-bold text-[var(--color-primary)] underline">Hapus filter kendaraan</button>}
    </section>
    <section id="kategori" className="mx-auto max-w-7xl px-4 pt-7 sm:px-6 sm:pt-10">
      <div className="flex items-end justify-between gap-3"><div><p className="text-[11px] font-extrabold uppercase tracking-[.16em] text-[var(--color-primary)]">Kategori spare part</p><h2 className="mt-1 text-xl font-extrabold tracking-tight sm:text-2xl">Belanja berdasarkan kategori</h2></div><span className="hidden text-xs text-slate-500 sm:block">Pilih kategori untuk mencari katalog</span></div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 sm:gap-3">{categories.filter(item=>!item.parent_id).map((item,index)=><button key={item.id} type="button" aria-pressed={selectedCategory===item.id} onClick={()=>{setSelectedCategory(selectedCategory===item.id?"":item.id);setQuery("");document.getElementById("katalog")?.scrollIntoView({behavior:"smooth"});}} className={"flex min-h-[94px] flex-col items-start justify-center rounded-2xl border p-3 text-left transition sm:min-h-[112px] sm:p-4 "+(selectedCategory===item.id?"border-orange-400 bg-orange-50":"border-slate-200 bg-white hover:border-orange-200 hover:bg-orange-50/50")}><span aria-hidden="true" className="grid h-9 w-9 place-items-center rounded-xl bg-orange-50 text-lg text-[var(--color-primary)] sm:h-11 sm:w-11 sm:text-xl">{["⚙","◉","ϟ","▧","◈","▤"][index%6]}</span><span className="mt-2 text-xs font-extrabold sm:text-sm">{item.name}</span><span className="mt-1 text-[10px] text-slate-500">{item.vehicle_scope==="all"?"Semua kendaraan":item.vehicle_scope==="motorcycle"?"Motor":item.vehicle_scope==="car"?"Mobil":"Komersial"}</span></button>)}</div>{selectedCategoryItem&&<div className="mt-3 rounded-2xl border border-orange-200 bg-orange-50/60 p-3 sm:p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-[10px] font-extrabold uppercase tracking-wider text-orange-700">Kategori terpilih</p><h3 className="mt-1 text-sm font-extrabold">{selectedCategoryItem.name}</h3><p className="mt-1 text-xs text-slate-600">Filter mencakup subkategori aktif di bawah kategori ini.</p></div><button type="button" onClick={()=>setSelectedCategory("")} className="rounded-lg border border-orange-300 bg-white px-3 py-2 text-xs font-bold text-orange-800">Hapus kategori</button></div>{selectedCategoryChildren.length>0&&<div className="mt-3 flex flex-wrap gap-2">{selectedCategoryChildren.map(child=><button key={child.id} type="button" aria-pressed={selectedCategory===child.id} onClick={()=>{setSelectedCategory(child.id);document.getElementById("katalog")?.scrollIntoView({behavior:"smooth"});}} className={"rounded-full border px-3 py-2 text-xs font-bold "+(selectedCategory===child.id?"border-orange-500 bg-orange-600 text-white":"border-orange-200 bg-white text-slate-700")}>{child.name}</button>)}</div>}</div>}{categoryError&&<p role="status" className="mt-3 text-xs text-amber-700">{categoryError}</p>}{!categoryError&&categories.length===0&&<p className="mt-3 text-sm text-slate-500">Belum ada kategori aktif.</p>}
    </section>
    <section id="katalog" className="mx-auto max-w-7xl px-4 py-7 sm:px-6 sm:py-10">
      {selectedCategoryItem&&<div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-orange-200 bg-orange-50 px-3 py-2 text-xs"><span className="font-bold">Kategori: {selectedCategoryItem.name}</span><button type="button" onClick={()=>setSelectedCategory("")} className="rounded-full border border-orange-300 bg-white px-3 py-1 font-bold text-[var(--color-primary)]">Hapus filter</button></div>}
      <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end"><div><p className="text-[10px] font-extrabold uppercase tracking-[.16em] text-[var(--color-primary)]">Katalog terverifikasi</p><h2 className="mt-1 text-xl font-black tracking-tight sm:text-2xl">Semua produk</h2><p className="mt-1 text-xs text-slate-500 sm:text-sm">Data live dari katalog publik OtoClinic. Tidak ada produk contoh.</p></div><span className="text-[10px] text-slate-500 sm:text-xs">Harga, stok, dan kecocokan perlu dikonfirmasi.</span></div>
      {loading ? <div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{[1,2,3,4].map(i=><div key={i} className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white p-5"><div className="h-4 w-2/3 rounded bg-slate-100"/><div className="mt-4 h-3 w-1/2 rounded bg-slate-100"/><div className="mt-12 h-5 w-1/3 rounded bg-slate-100"/></div>)}</div>
      : error ? <div role="alert" className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">{error}</div>
     
      : filtered.length===0 ? <div className="mt-7 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><PackageSearch className="mx-auto text-slate-400" size={32}/><h3 className="mt-3 font-bold">{query ? "Produk tidak ditemukan" : "Belum ada produk yang dipublikasikan"}</h3><p className="mt-2 text-sm text-slate-500">{query ? "Coba nama atau nomor part yang berbeda." : "Produk akan tampil setelah katalog nyata melewati proses review dan publikasi."}</p></div>
      : <>{cartNotice&&<p role="status" className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{cartNotice}</p>}<div className="mt-5 grid grid-cols-2 gap-2 sm:mt-7 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4">{filtered.map(p=><article key={p.id} className="flex min-w-0 flex-col rounded-xl border border-slate-200 bg-white p-2.5 transition hover:-translate-y-0.5 hover:shadow-md sm:rounded-2xl sm:p-5"><div className="flex h-28 items-center justify-center overflow-hidden rounded-lg bg-slate-50 sm:h-40 sm:rounded-xl">{p.image_url ? <img src={p.image_url} alt={p.images?.find(image=>image.is_primary)?.alt_text || ("Foto produk " + p.name)} loading="lazy" className="h-full w-full object-contain" /> : <div className="flex flex-col items-center gap-2 text-slate-400"><Wrench size={30} className="text-slate-300"/><span className="text-[11px]">Foto belum tersedia</span></div>}</div><p className="mt-3 text-[10px] font-bold uppercase tracking-wide text-slate-500 sm:mt-4 sm:text-[11px]">{p.category}</p><h3 className="mt-1 line-clamp-2 text-xs font-bold leading-4 sm:text-sm sm:leading-5"><Link href={"/products/"+p.id} className="hover:text-[var(--color-primary)] focus-visible:underline">{p.name}</Link></h3><p className="mt-1 line-clamp-1 text-[10px] text-slate-500 sm:mt-2 sm:text-xs">{p.brand || "Merek belum dicantumkan"}{p.part_number ? " · "+p.part_number : ""}</p><Link href={"/products/"+p.id} className="mt-2 inline-flex min-h-8 items-center text-[10px] font-bold text-[var(--color-primary)] underline sm:text-xs">Detail produk</Link><span className="mt-2 w-fit rounded-full bg-slate-100 px-2 py-1 text-[9px] font-semibold leading-3 text-slate-600 sm:mt-3 sm:px-2.5 sm:text-[11px]">{conditionLabels[p.condition] || p.condition}</span><div className="mt-auto pt-3 sm:pt-5"><p className="text-sm font-extrabold sm:text-base">{money(p.retail_price)}</p><span className={"mt-2 inline-flex max-w-full rounded-full px-2 py-1 text-[9px] font-bold leading-4 sm:text-[10px] "+stockTone(p.stock_status)}>{stockLabel(p.stock_status)}</span><p className="mt-1 text-[9px] leading-4 text-slate-400 sm:text-[11px]">{p.stock_checked_at?"Pembaruan stok: "+new Date(p.stock_checked_at).toLocaleString("id-ID"):"Belum ada catatan inventori terverifikasi"}</p>{["in_stock","low_stock"].includes(p.stock_status||"unverified")?<button disabled={cartBusy===p.id} onClick={()=>void addToCart(p.id)} className="mt-3 inline-flex min-h-10 w-full items-center justify-center gap-1 rounded-lg bg-[var(--color-primary)] px-2 py-2 text-[10px] font-bold text-white disabled:opacity-50 sm:gap-2 sm:rounded-xl sm:px-3 sm:text-sm">{cartBusy===p.id?"Memproses…":<><ShoppingCart size={15}/> Tambah ke keranjang</>}</button>:<a href="#permintaan" className="mt-3 inline-flex min-h-10 w-full items-center justify-center gap-1 rounded-lg border border-orange-200 bg-orange-50 px-2 py-2 text-[10px] font-bold text-orange-800 sm:gap-2 sm:rounded-xl sm:px-3 sm:text-sm">Minta bantuan sourcing</a>}</div></article>)}</div></>}
    </section>
    <section className="mx-auto max-w-7xl px-3 pt-7 sm:px-6 sm:pt-10" aria-labelledby="koleksi-title">
      <div className="flex items-end justify-between gap-3"><div><p className="text-[10px] font-extrabold uppercase tracking-[.16em] text-[var(--color-primary)]">Temukan kebutuhan Anda</p><h2 id="koleksi-title" className="mt-1 text-lg font-black tracking-tight sm:text-2xl">Pilihan katalog</h2></div><a href="#katalog" className="text-[11px] font-extrabold text-[var(--color-primary)] sm:text-xs">Lihat semua</a></div>
      <div className="collection-rail mt-3 flex flex-wrap gap-2 pb-2" aria-label="Kategori koleksi katalog">
        {[["Semua produk","katalog"],["Best seller","shelf-best-seller"],["Popular","shelf-popular"],["Secondary","shelf-secondary"],["Produk baru","shelf-new"],["Promo","shelf-promo"],["Iklan","shelf-ads"]].map(([label,id],i)=><a key={id} href={"#"+id} className={`shrink-0 rounded-full border px-4 py-2.5 text-xs font-extrabold ${i===0?"border-[var(--color-primary)] bg-[var(--color-primary)] text-white":"border-slate-200 bg-white text-slate-700 hover:border-orange-200 hover:text-[var(--color-primary)]"}`}>{label}</a>)}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3">
        {[["tile-best-seller","Best Seller","Produk dengan penjualan terverifikasi.","shelf-best-seller"],["tile-popular","Popular","Produk dengan minat pencarian terukur.","shelf-popular"],["tile-secondary","Secondary","Pilihan part pendukung dan alternatif.","shelf-secondary"],["tile-new","Produk Baru","Produk yang baru dipublikasikan.","shelf-new"],["tile-promo","Promo","Penawaran dengan periode dan syarat yang jelas.","shelf-promo"],["tile-ads","Iklan & Sponsor","Slot promosi yang dikelola secara resmi.","shelf-ads"]].map(([id,title,description,target],i)=><a key={id} id={id} href={"#"+target} className="collection-tile flex min-h-[94px] min-w-0 flex-col justify-between rounded-xl border border-slate-200 bg-white p-3 sm:min-h-[112px] sm:rounded-2xl sm:p-4"><span className={`grid h-8 w-8 place-items-center rounded-lg ${i===4||i===5?"bg-orange-50 text-[var(--color-primary)]":"bg-slate-100 text-slate-700"}`}>{["▦","⌕","⚙","✦","%","▣"][i]}</span><span><strong className="block text-xs font-extrabold sm:text-sm">{title}</strong><small className="mt-1 block text-[10px] leading-4 text-slate-500">{description}</small></span></a>)}
      </div>
      <p className="mt-2 text-[10px] leading-4 text-slate-500">Label Best Seller, Popular, Promo, dan Iklan hanya akan menampilkan produk setelah data kurasi/penjualan/promosi tersedia. Tidak ada diskon atau statistik yang dibuat-buat.</p>
    </section>
    <section className="mx-auto max-w-7xl px-3 pt-5 sm:px-6 sm:pt-7" aria-label="Koleksi produk dari data katalog">
      {[
        {id:"shelf-best-seller",title:"Best Seller",description:"Produk terlaris berdasarkan transaksi terverifikasi.",items:[],empty:"Belum tersedia: data transaksi terverifikasi belum tersedia."},
        {id:"shelf-popular",title:"Popular",description:"Produk populer berdasarkan metrik penggunaan yang terukur.",items:[],empty:"Belum tersedia: metrik popularitas belum tersedia."},
        {id:"shelf-secondary",title:"Secondary & alternatif",description:"Part bekas, rekondisi, remanufaktur, dan alternatif.",items:secondaryProducts,empty:"Belum ada produk secondary yang dipublikasikan."},
        {id:"shelf-new",title:"Produk baru",description:"Produk katalog yang dipublikasikan dalam 30 hari terakhir.",items:recentProducts,empty:"Belum ada produk baru dalam periode 30 hari terakhir."},
        {id:"shelf-promo",title:"Promo aktif",description:"Promosi dengan periode dan ketentuan yang berlaku.",items:[],empty:"Belum ada kampanye promo aktif yang terhubung."},
        {id:"shelf-ads",title:"Iklan & sponsor",description:"Slot iklan komersial yang ditandai secara transparan.",items:[],empty:"Belum ada kampanye iklan aktif yang terhubung."}
      ].map(shelf=><section key={shelf.id} id={shelf.id} className="mb-5 scroll-mt-24 rounded-2xl border border-slate-200 bg-white p-3 sm:p-4">
        <div className="flex items-start justify-between gap-3"><div><h2 className="text-sm font-black sm:text-base">{shelf.title}</h2><p className="mt-1 text-[10px] leading-4 text-slate-500 sm:text-xs">{shelf.description}</p></div><a href="#katalog" className="shrink-0 text-[10px] font-extrabold text-[var(--color-primary)] sm:text-xs">Semua produk</a></div>
        {shelf.items.length>0?<div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">{shelf.items.slice(0,4).map(p=><article key={p.id} className="min-w-0 rounded-xl border border-slate-100 p-2.5 sm:p-3"><Link href={"/products/"+p.id} className="block"><div className="flex h-24 items-center justify-center overflow-hidden rounded-lg bg-slate-50 sm:h-32">{p.image_url?<img src={p.image_url} alt={p.images?.find(image=>image.is_primary)?.alt_text||("Foto produk "+p.name)} loading="lazy" className="h-full w-full object-contain"/>:<Wrench size={25} className="text-slate-300"/>}</div><p className="mt-2 line-clamp-2 text-xs font-bold leading-4">{p.name}</p><p className="mt-1 text-[10px] text-slate-500">{p.brand||p.category}</p><p className="mt-2 text-xs font-black">{money(p.retail_price)}</p></Link></article>)}</div>:<p className="mt-3 rounded-lg bg-slate-50 px-3 py-2.5 text-[10px] leading-4 text-slate-600 sm:text-xs">{shelf.empty}</p>}
      </section>)}
    </section>
    <section id="cara-kerja" className="border-y border-slate-200 bg-white"><div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-14"><h2 className="text-2xl font-extrabold">Belanja dengan informasi yang jelas</h2><div className="mt-6 grid gap-4 md:grid-cols-3">{[["01","Pilih kendaraan","Cocokkan merek, model, tahun, dan varian."],["02","Periksa kondisi","Bedakan barang baru, copotan, rekondisi, dan lainnya."],["03","Konfirmasi pesanan","Pastikan harga, ketersediaan, garansi, dan fitment sebelum pembayaran."]].map(s=><div key={s[0]} className="rounded-2xl border border-slate-200 p-5"><span className="text-sm font-extrabold text-[var(--color-primary)]">{s[0]}</span><h3 className="mt-3 font-bold">{s[1]}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{s[2]}</p></div>)}</div></div></section>
    <footer id="bantuan" className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6"><div><p className="font-extrabold text-slate-800">OtoClinic</p><p className="mt-1">Marketplace spare part otomotif Indonesia.</p></div><p className="flex items-center gap-2"><CircleHelp size={15}/> Selalu konfirmasi fitment, harga, stok, dan garansi sebelum transaksi.</p><div className="flex flex-wrap items-center gap-4"><a href="#katalog" className="flex items-center gap-1 font-bold text-[var(--color-primary)]">Jelajahi katalog <ArrowRight size={14}/></a><Link href="/supplier" className="font-bold text-slate-600 underline underline-offset-4">Portal mitra supplier</Link></div></footer>
  <nav className="mobile-bottom-nav" aria-label="Navigasi utama"><Link href="/" aria-current="page"><House size={22}/><small>Beranda</small></Link><a href="#kategori"><Grid2X2 size={22}/><small>Kategori</small></a><a href="#permintaan"><Plus size={24}/><small>Request</small></a><Link href="/account"><Heart size={22}/><small>Favorit</small></Link><Link href="/account"><UserRound size={22}/><small>Akun</small></Link></nav><section id="permintaan" className="mx-auto mb-8 mt-8 max-w-7xl scroll-mt-24 px-3 sm:px-6"><div className="grid gap-5 rounded-3xl border border-orange-200 bg-orange-50/70 p-4 sm:p-6 lg:grid-cols-[.8fr_1.2fr] lg:gap-8 lg:p-8"><div><span className="inline-flex rounded-full bg-white px-3 py-1.5 text-[10px] font-extrabold uppercase tracking-wider text-orange-700">Layanan sourcing</span><h2 className="mt-3 text-xl font-black sm:text-2xl">Tidak menemukan spare part?</h2><p className="mt-2 text-sm leading-6 text-slate-600">Kirim detail part dan kendaraan. Permintaan disimpan ke sistem OtoClinic agar dapat ditindaklanjuti tim operasional.</p><ul className="mt-4 space-y-2 text-xs leading-5 text-slate-600"><li>• Nomor part/OEM jika tersedia</li><li>• Merek, model, dan tahun kendaraan</li><li>• Jumlah yang dibutuhkan dan catatan tambahan</li></ul><p className="mt-4 rounded-xl border border-orange-200 bg-white p-3 text-xs leading-5 text-slate-600">Pengiriman permintaan memerlukan akun pelanggan aktif. Form ini tidak membuat pesanan atau pembayaran.</p></div><form onSubmit={submitSourcingRequest} className="grid min-w-0 gap-3 rounded-2xl border border-orange-100 bg-white p-4 sm:grid-cols-2 sm:p-5"><label className="min-w-0 text-xs font-bold text-slate-700 sm:col-span-2">Nama spare part <span className="text-rose-600">*</span><input required minLength={2} maxLength={180} value={requestPartName} onChange={e=>setRequestPartName(e.target.value)} className="mt-1.5 min-h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-orange-400" placeholder="Contoh: kampas rem depan"/></label><label className="min-w-0 text-xs font-bold text-slate-700">Nomor part / OEM<input maxLength={120} value={requestPartNumber} onChange={e=>setRequestPartNumber(e.target.value)} className="mt-1.5 min-h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-orange-400" placeholder="Jika diketahui"/></label><label className="min-w-0 text-xs font-bold text-slate-700">Jumlah dibutuhkan<input required type="number" min={1} max={100} value={requestQuantity} onChange={e=>setRequestQuantity(e.target.value)} className="mt-1.5 min-h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-orange-400"/></label><label className="min-w-0 text-xs font-bold text-slate-700">Merek kendaraan<input maxLength={100} value={requestMake} onChange={e=>setRequestMake(e.target.value)} className="mt-1.5 min-h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-orange-400" placeholder="Toyota, Honda, Yamaha…"/></label><label className="min-w-0 text-xs font-bold text-slate-700">Model kendaraan<input maxLength={120} value={requestModel} onChange={e=>setRequestModel(e.target.value)} className="mt-1.5 min-h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-orange-400" placeholder="Avanza, Vario…"/></label><label className="min-w-0 text-xs font-bold text-slate-700">Tahun kendaraan<input type="number" min={1950} max={2100} value={requestYear} onChange={e=>setRequestYear(e.target.value)} className="mt-1.5 min-h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-orange-400" placeholder="2021"/></label><label className="min-w-0 text-xs font-bold text-slate-700">Nomor WhatsApp (opsional)<input maxLength={40} value={requestPhone} onChange={e=>setRequestPhone(e.target.value)} className="mt-1.5 min-h-11 w-full min-w-0 rounded-xl border border-slate-200 px-3 text-sm font-normal outline-none focus:border-orange-400" placeholder="+62…"/></label><label className="min-w-0 text-xs font-bold text-slate-700 sm:col-span-2">Catatan tambahan<textarea maxLength={2000} rows={3} value={requestDetails} onChange={e=>setRequestDetails(e.target.value)} className="mt-1.5 w-full min-w-0 rounded-xl border border-slate-200 p-3 text-sm font-normal outline-none focus:border-orange-400" placeholder="Tipe/varian mesin, kebutuhan khusus, atau detail lain"/></label>{requestNotice&&<p role={requestNotice.kind==="error"?"alert":"status"} className={"rounded-xl p-3 text-xs leading-5 sm:col-span-2 "+(requestNotice.kind==="success"?"border border-emerald-200 bg-emerald-50 text-emerald-800":"border border-rose-200 bg-rose-50 text-rose-800")}>{requestNotice.text}</p>}<button disabled={requestBusy} type="submit" className="inline-flex min-h-11 items-center justify-center rounded-xl bg-[var(--color-primary)] px-4 py-3 text-sm font-extrabold text-white disabled:cursor-wait disabled:opacity-60 sm:col-span-2">{requestBusy?"Menyimpan permintaan…":"Kirim permintaan sourcing"}</button></form></div></section>
  </main>;
}
