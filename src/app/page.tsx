"use client";
import Link from "next/link";

import { useEffect, useState } from "react";
import { ArrowRight, CarFront, Search, ShieldCheck, Wrench, Bike, PackageSearch, CircleHelp } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type Product = { id: string; name: string; sku: string; brand: string | null; part_number: string | null; category: string; condition: string; retail_price: number | null; status: string };

const conditionLabels: Record<string,string> = {
  new_oem: "Baru · OEM", new_aftermarket: "Baru · Aftermarket", used: "Bekas / copotan",
  refurbished: "Rekondisi", remanufactured: "Remanufaktur", damaged_for_parts: "Untuk kanibal part"
};

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const supabase = getSupabaseBrowserClient();

  useEffect(() => {
    let active = true;
    async function load() {
      if (!supabase) { setLoading(false); return; }
      const { data, error: fetchError } = await supabase
        .from("products")
        .select("id,name,sku,brand,part_number,category,condition,retail_price,status")
        .eq("status", "published")
        .order("name", { ascending: true })
        .limit(8);
      if (!active) return;
      if (fetchError) setError("Katalog belum dapat dimuat. Silakan coba kembali nanti.");
      else setProducts((data ?? []) as Product[]);
      setLoading(false);
    }
    void load();
    return () => { active = false; };
  }, [supabase]);

  const filtered = products.filter(p => [p.name,p.sku,p.brand ?? "",p.part_number ?? "",p.category].some(v => v.toLowerCase().includes(query.toLowerCase())));
  const money = (n: number | null) => n === null ? "Hubungi untuk harga" : new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(n);

  return <main className="min-h-screen">
    <header className="sticky top-0 z-20 border-b border-[var(--color-border)] bg-white/95 backdrop-blur">
      <div className="mx-auto flex h-[72px] max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-3" aria-label="OtoClinic beranda">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-primary)] text-white"><Wrench size={22}/></span>
          <span><strong className="block text-lg font-extrabold tracking-tight">OtoClinic</strong><span className="block text-[10px] font-semibold uppercase tracking-[.15em] text-slate-500">Spare part otomotif</span></span>
        </Link>
        <nav className="hidden items-center gap-6 text-sm font-semibold text-slate-600 md:flex"><a href="#katalog" className="hover:text-[var(--color-primary)]">Katalog</a><a href="#cara-kerja" className="hover:text-[var(--color-primary)]">Cara kerja</a><a href="#bantuan" className="hover:text-[var(--color-primary)]">Bantuan</a></nav>
        <a href="#katalog" className="rounded-xl bg-[var(--color-primary)] px-4 py-2.5 text-sm font-bold text-white hover:opacity-90">Cari spare part</a>
      </div>
    </header>
    <section className="relative overflow-hidden bg-[var(--color-ink)] text-white">
      <div className="mx-auto grid max-w-7xl items-center gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[1.2fr_.8fr] lg:py-24">
        <div><span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold text-orange-200"><ShieldCheck size={14}/> Informasi lebih jelas, pilihan lebih tepat</span>
          <h1 className="mt-6 max-w-2xl text-4xl font-extrabold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">Spare part tepat. <span className="text-orange-300">Kendaraan tetap jalan.</span></h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">Cari suku cadang mobil dan motor dengan informasi kondisi, kecocokan kendaraan, serta garansi yang transparan.</p>
          <form onSubmit={e=>{e.preventDefault();document.getElementById("katalog")?.scrollIntoView({behavior:"smooth"});}} className="mt-8 flex max-w-2xl gap-2 rounded-2xl bg-white p-2 shadow-xl shadow-black/10"><Search className="ml-2 mt-3 shrink-0 text-slate-400" size={21}/><input aria-label="Cari nama spare part atau nomor part" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Nama spare part, merek, atau nomor part..." className="min-w-0 flex-1 bg-transparent px-1 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 sm:text-base"/><button className="rounded-xl bg-[var(--color-primary)] px-4 py-2 text-sm font-bold text-white sm:px-6">Cari</button></form>
          <p className="mt-3 text-xs text-slate-400">Pastikan tipe dan tahun kendaraan sebelum membeli.</p>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:gap-4"><div className="rounded-3xl border border-white/10 bg-white/[.06] p-5 sm:p-7"><CarFront size={30} className="text-orange-300"/><h2 className="mt-5 text-lg font-bold">Spare part mobil</h2><p className="mt-2 text-sm leading-6 text-slate-300">OEM, aftermarket, bekas, dan rekondisi.</p></div><div className="mt-8 rounded-3xl border border-white/10 bg-white/[.06] p-5 sm:p-7"><Bike size={30} className="text-orange-300"/><h2 className="mt-5 text-lg font-bold">Spare part motor</h2><p className="mt-2 text-sm leading-6 text-slate-300">Pilihan part sesuai kendaraan dan kebutuhan.</p></div><div className="col-span-2 flex items-start gap-4 rounded-2xl border border-white/10 bg-white/[.06] p-5"><ShieldCheck className="mt-1 shrink-0 text-emerald-300" size={24}/><div><p className="font-bold">Fitment dan kondisi harus jelas</p><p className="mt-1 text-sm text-slate-300">Status kecocokan ditampilkan berdasarkan bukti yang tersedia, bukan asumsi.</p></div></div></div>
      </div>
    </section>
    <section id="katalog" className="mx-auto max-w-7xl px-4 py-14 sm:px-6 sm:py-16">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-extrabold uppercase tracking-[.18em] text-[var(--color-primary)]">Katalog</p><h2 className="mt-2 text-2xl font-extrabold tracking-tight sm:text-3xl">Spare part pilihan</h2><p className="mt-2 text-sm text-slate-500">Produk yang ditampilkan berasal dari katalog publik OtoClinic.</p></div><span className="text-xs text-slate-500">Harga dan stok perlu dikonfirmasi sebelum checkout.</span></div>
      {loading ? <div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{[1,2,3,4].map(i=><div key={i} className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white p-5"><div className="h-4 w-2/3 rounded bg-slate-100"/><div className="mt-4 h-3 w-1/2 rounded bg-slate-100"/><div className="mt-12 h-5 w-1/3 rounded bg-slate-100"/></div>)}</div>
      : error ? <div role="alert" className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">{error}</div>
      : !supabase ? <div className="mt-7 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><PackageSearch className="mx-auto text-slate-400" size={32}/><h3 className="mt-3 font-bold">Katalog sedang disiapkan</h3><p className="mx-auto mt-2 max-w-lg text-sm text-slate-500">Koneksi publik Supabase belum dikonfigurasi di environment aplikasi. Tidak ada produk contoh yang ditampilkan.</p></div>
      : filtered.length===0 ? <div className="mt-7 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"><PackageSearch className="mx-auto text-slate-400" size={32}/><h3 className="mt-3 font-bold">{query ? "Produk tidak ditemukan" : "Belum ada produk yang dipublikasikan"}</h3><p className="mt-2 text-sm text-slate-500">{query ? "Coba nama atau nomor part yang berbeda." : "Produk akan tampil setelah katalog nyata melewati proses review dan publikasi."}</p></div>
      : <div className="mt-7 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">{filtered.map(p=><article key={p.id} className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:shadow-md"><div className="flex h-24 items-center justify-center rounded-xl bg-slate-50"><Wrench size={30} className="text-slate-300"/></div><p className="mt-4 text-[11px] font-bold uppercase tracking-wide text-slate-500">{p.category}</p><h3 className="mt-1 font-bold leading-5">{p.name}</h3><p className="mt-2 text-xs text-slate-500">{p.brand || "Merek belum dicantumkan"}{p.part_number ? " · "+p.part_number : ""}</p><span className="mt-3 w-fit rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">{conditionLabels[p.condition] || p.condition}</span><div className="mt-auto pt-5"><p className="text-base font-extrabold">{money(p.retail_price)}</p><p className="mt-1 text-[11px] text-slate-400">Fitment dan stok dikonfirmasi saat pemesanan</p></div></article>)}</div>}
    </section>
    <section id="cara-kerja" className="border-y border-slate-200 bg-white"><div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-14"><h2 className="text-2xl font-extrabold">Belanja dengan informasi yang jelas</h2><div className="mt-6 grid gap-4 md:grid-cols-3">{[["01","Pilih kendaraan","Cocokkan merek, model, tahun, dan varian."],["02","Periksa kondisi","Bedakan barang baru, copotan, rekondisi, dan lainnya."],["03","Konfirmasi pesanan","Pastikan harga, ketersediaan, garansi, dan fitment sebelum pembayaran."]].map(s=><div key={s[0]} className="rounded-2xl border border-slate-200 p-5"><span className="text-sm font-extrabold text-[var(--color-primary)]">{s[0]}</span><h3 className="mt-3 font-bold">{s[1]}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{s[2]}</p></div>)}</div></div></section>
    <footer id="bantuan" className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6"><div><p className="font-extrabold text-slate-800">OtoClinic</p><p className="mt-1">Marketplace spare part otomotif Indonesia.</p></div><p className="flex items-center gap-2"><CircleHelp size={15}/> Selalu konfirmasi fitment, harga, stok, dan garansi sebelum transaksi.</p><a href="#katalog" className="flex items-center gap-1 font-bold text-[var(--color-primary)]">Jelajahi katalog <ArrowRight size={14}/></a></footer>
  </main>;
}
