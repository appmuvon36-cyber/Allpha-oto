"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, Boxes, ClipboardList, LogOut, Package, RefreshCw, ShieldCheck, Truck, Wrench, ClipboardCheck } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type Counts = { products: number; suppliers: number; fitments: number; inventory: number };
type ProductRow = { id: string; sku: string; name: string; category: string; condition: string; status: string; retail_price: number | null };

export default function AdminPage() {
  const router = useRouter();
  const [loading,setLoading] = useState(true);
  const [signedIn,setSignedIn] = useState(false);
  const [authorized,setAuthorized] = useState(false);
  const [email,setEmail] = useState("");
  const [counts,setCounts] = useState<Counts>({products:0,suppliers:0,fitments:0,inventory:0});
  const [recent,setRecent] = useState<ProductRow[]>([]);
  const [notice,setNotice] = useState("");
  const [error,setError] = useState("");
  const supabase = getSupabaseBrowserClient();

  async function load() {
    setLoading(true); setError("");
    if (!supabase) { setError("Environment Supabase belum dikonfigurasi. Tambahkan URL dan anon key melalui environment deployment."); setLoading(false); return; }
    const {data:{user},error:authError} = await supabase.auth.getUser();
    if (authError || !user) { setSignedIn(false); setAuthorized(false); setLoading(false); return; }
    setSignedIn(true); setEmail(user.email ?? "");
    const {data:profile,error:profileError} = await supabase.from("user_profiles").select("role,is_active").eq("id",user.id).maybeSingle();
    const role = profile?.role;
    const canAdmin = Boolean(profile?.is_active) && ["admin","catalog_editor","inventory_manager","order_manager","moderator"].includes(role ?? "");
    if (profileError || !canAdmin) { setAuthorized(false); setError("Akun tidak memiliki role operasional yang diperlukan. Hubungi administrator untuk pemberian akses."); setLoading(false); return; }
    setAuthorized(true);
    const [products,suppliers,fitments,inventory,latest] = await Promise.all([
      supabase.from("products").select("id",{count:"exact",head:true}),
      supabase.from("suppliers").select("id",{count:"exact",head:true}),
      supabase.from("product_fitments").select("id",{count:"exact",head:true}),
      supabase.from("inventory_ledger").select("id",{count:"exact",head:true}),
      supabase.from("products").select("id,sku,name,category,condition,status,retail_price").order("created_at",{ascending:false}).limit(6)
    ]);
    const firstError = products.error || suppliers.error || fitments.error || inventory.error || latest.error;
    if (firstError) setError("Sebagian data operasional tidak dapat dimuat. Periksa kebijakan RLS dan kolom schema; tidak ada data contoh yang digunakan.");
    setCounts({products:products.count ?? 0,suppliers:suppliers.count ?? 0,fitments:fitments.count ?? 0,inventory:inventory.count ?? 0});
    setRecent((latest.data ?? []) as ProductRow[]);
    setLoading(false);
  }

  useEffect(()=>{ void load(); },[]);

  async function signOut() {
    if (supabase) await supabase.auth.signOut();
    router.push("/");
  }
  const money=(n:number|null)=>n===null?"Belum ditetapkan":new Intl.NumberFormat("id-ID",{style:"currency",currency:"IDR",maximumFractionDigits:0}).format(n);
  const statusLabel:Record<string,string>={draft:"Draft",review:"Review",approved:"Disetujui",published:"Tayang",rejected:"Ditolak",archived:"Arsip"};
  const tiles=[
    {label:"SKU katalog",value:counts.products,icon:Package,description:"Jumlah baris produk yang dapat diakses"},
    {label:"Supplier",value:counts.suppliers,icon:Truck,description:"Jumlah mitra pemasok tercatat"},
    {label:"Data fitment",value:counts.fitments,icon:Wrench,description:"Relasi produk dan varian kendaraan"},
    {label:"Ledger inventori",value:counts.inventory,icon:Boxes,description:"Catatan pergerakan inventori"}
  ];

  return <main className="min-h-screen bg-[var(--color-canvas)]">
    <header className="border-b border-[var(--color-border)] bg-white"><div className="mx-auto flex min-h-[72px] max-w-7xl items-center justify-between gap-4 px-4 sm:px-6"><a href="/" className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-primary)] text-white"><Wrench size={21}/></span><span><strong className="block text-lg font-extrabold">OtoClinic</strong><span className="block text-[10px] font-bold uppercase tracking-[.15em] text-slate-500">Operations</span></span></a><div className="flex items-center gap-2">{signedIn&&<span className="hidden text-xs text-slate-500 sm:block">{email}</span>}<button onClick={()=>void load()} className="flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-xs font-bold hover:bg-slate-50"><RefreshCw size={14}/> Refresh</button>{signedIn&&<button onClick={()=>void signOut()} className="flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-xs font-bold hover:bg-slate-50"><LogOut size={14}/> Keluar</button>}</div></div></header>
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-extrabold uppercase tracking-[.18em] text-[var(--color-primary)]">Workspace</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight">Ringkasan operasional</h1><p className="mt-2 text-sm text-slate-500">Angka dihitung dari data Supabase yang dapat diakses akun Anda.</p></div><span className="flex w-fit items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-800"><ShieldCheck size={14}/> Akses terkontrol</span></div>
      {loading?<div className="mt-8 rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500">Memeriksa sesi, role, dan data operasional…</div>
      :!signedIn?<section className="mt-8 max-w-xl rounded-2xl border border-slate-200 bg-white p-6 sm:p-8"><ShieldCheck className="text-[var(--color-primary)]" size={28}/><h2 className="mt-4 text-xl font-extrabold">Masuk diperlukan</h2><p className="mt-2 text-sm leading-6 text-slate-500">Dashboard operasional hanya tersedia bagi pengguna terautentikasi dengan role yang sesuai. Pastikan halaman login/Auth telah dikonfigurasi untuk environment ini.</p><button onClick={()=>router.push("/")} className="mt-5 flex items-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 py-3 text-sm font-bold text-white">Kembali ke OtoClinic <ArrowRight size={16}/></button>{error&&<p role="alert" className="mt-4 text-xs text-amber-800">{error}</p>}</section>
      :!authorized?<div role="alert" className="mt-8 flex max-w-2xl gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900"><AlertCircle className="shrink-0" size={20}/><div><p className="font-bold">Akses belum diberikan</p><p className="mt-1">{error||"Akun tidak memiliki izin."}</p></div></div>
      :<><div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-sm text-slate-500">Kelola katalog dan tinjau bukti kecocokan kendaraan.</p><button onClick={()=>router.push("/catalog")} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 text-sm font-bold text-white hover:opacity-90"><ClipboardCheck size={16}/> Buka katalog & fitment <ArrowRight size={15}/></button></div><div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{tiles.map(t=><article key={t.label} className="rounded-2xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-50 text-[var(--color-primary)]"><t.icon size={20}/></span><span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Live query</span></div><p className="mt-5 text-xs font-semibold text-slate-500">{t.label}</p><p className="mt-1 text-3xl font-extrabold tabular-nums">{new Intl.NumberFormat("id-ID").format(t.value)}</p><p className="mt-2 text-xs text-slate-400">{t.description}</p></article>)}</div>
      {error&&<div role="alert" className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{error}</div>}
      <section className="mt-7 overflow-hidden rounded-2xl border border-slate-200 bg-white"><div className="flex items-center justify-between border-b border-slate-100 p-5 sm:px-6"><div><h2 className="font-extrabold">Produk terbaru</h2><p className="mt-1 text-xs text-slate-500">Data nyata yang dikembalikan oleh Supabase RLS.</p></div><span className="flex items-center gap-2 text-xs text-slate-500"><ClipboardList size={15}/> {recent.length} baris</span></div>{recent.length===0?<div className="p-8 text-center"><Package size={28} className="mx-auto text-slate-300"/><p className="mt-3 font-bold">Belum ada data produk</p><p className="mt-1 text-sm text-slate-500">Tidak ada contoh produk yang dibuat otomatis.</p></div>:<div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500"><tr>{["SKU","Produk","Kategori","Kondisi","Harga","Status"].map(s=><th key={s} className="px-5 py-3 font-bold">{s}</th>)}</tr></thead><tbody>{recent.map(p=><tr key={p.id} className="border-t border-slate-100 text-xs"><td className="px-5 py-4 font-mono">{p.sku}</td><td className="px-5 py-4 font-bold">{p.name}</td><td className="px-5 py-4">{p.category}</td><td className="px-5 py-4">{p.condition}</td><td className="px-5 py-4 font-bold">{money(p.retail_price)}</td><td className="px-5 py-4"><span className="rounded-full bg-slate-100 px-2.5 py-1 font-bold">{statusLabel[p.status]??p.status}</span></td></tr>)}</tbody></table></div>}</section><p className="mt-5 text-xs text-slate-400">Dashboard ini hanya membaca data. Aksi perubahan produk, stok, supplier, dan pesanan belum diaktifkan sebelum API otorisasi dan audit selesai.</p></>}
    </div>
  </main>;
}
