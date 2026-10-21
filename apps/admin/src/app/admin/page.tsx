"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle, ArrowRight, Boxes, ClipboardCheck, ClipboardList, FileClock,
  LogOut, Package, RefreshCw, ShieldCheck, Truck, Users, Wrench, CreditCard,
  RotateCcw, Activity,
} from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
type Metric = { value: number | null; available: boolean };
type ProductRow = { id: string; sku: string | null; name: string; category: string | null; condition: string; status: string; retail_price: number | null; updated_at: string };
type Overview = { generated_at: string; role: string; metrics: Record<string, Metric>; latest_products: ProductRow[] };

const money = (value: number | null) => value === null ? "Belum ditetapkan" : new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(value);
const number = (value: number) => new Intl.NumberFormat("id-ID").format(value);
const roleLabels: Record<string, string> = {
  admin: "Administrator", catalog_editor: "Editor katalog", inventory_manager: "Manajer inventori",
  order_manager: "Manajer pesanan", moderator: "Moderator", supplier: "Pemasok", customer: "Pelanggan",
};
const statusLabels: Record<string, string> = {
  draft: "Draft", review: "Menunggu review", approved: "Disetujui", published: "Tayang",
  rejected: "Ditolak", archived: "Arsip", needs_review: "Perlu review", verified: "Terverifikasi",
};

export default function AdminPage() {
  const router = useRouter();
  const supabase = getSupabaseBrowserClient();
  const [loading, setLoading] = useState(true);
  const [signedIn, setSignedIn] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [email, setEmail] = useState("");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    if (!supabase) {
      setError("Environment autentikasi belum dikonfigurasi. Periksa konfigurasi Supabase pada deployment Admin.");
      setLoading(false);
      return;
    }
    try {
      const { data: { session }, error: authError } = await supabase.auth.getSession();
      if (authError) throw new Error("Sesi tidak dapat diperiksa. Silakan masuk kembali.");
      if (!session?.access_token) {
        setSignedIn(false);
        setAuthorized(false);
        setOverview(null);
        setLoading(false);
        return;
      }
      setSignedIn(true);
      setEmail(session.user.email ?? "");
      const response = await fetch(API + "/v1/admin/overview", {
        headers: { Authorization: "Bearer " + session.access_token, Accept: "application/json" },
        cache: "no-store",
      });
      if (response.status === 401) {
        await supabase.auth.signOut();
        setSignedIn(false);
        setAuthorized(false);
        setOverview(null);
        setError("Sesi telah berakhir. Silakan masuk kembali.");
        setLoading(false);
        return;
      }
      if (response.status === 403) {
        setAuthorized(false);
        setOverview(null);
        setError("Akun tidak memiliki role operasional yang diperlukan.");
        setLoading(false);
        return;
      }
      if (!response.ok) throw new Error("Data operasional tidak dapat dimuat (HTTP " + response.status + ").");
      const data = await response.json() as Overview;
      setOverview(data);
      setAuthorized(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Data operasional tidak dapat dimuat.");
    } finally {
      setLoading(false);
    }
  }, [supabase]);

  useEffect(() => { void load(); }, [load]);

  async function signOut() {
    if (supabase) await supabase.auth.signOut();
    router.replace("/login");
  }

  const primaryTiles = [
    { key: "products", label: "SKU katalog", icon: Package, note: "Produk dalam cakupan role" },
    { key: "suppliers", label: "Pemasok", icon: Truck, note: "Mitra pemasok tercatat" },
    { key: "inventory_movements", label: "Mutasi inventori", icon: Boxes, note: "Riwayat pergerakan stok" },
    { key: "orders", label: "Pesanan", icon: ClipboardList, note: "Pesanan dalam cakupan role" },
  ];
  const queues = [
    { key: "products_review", label: "Review katalog", href: "/catalog", icon: Package },
    { key: "fitments_review", label: "Review fitment", href: "/catalog", icon: Wrench },
    { key: "suppliers_review", label: "Review pemasok", href: "/suppliers", icon: Truck },
    { key: "supplier_offers_review", label: "Review penawaran", href: "/suppliers", icon: ClipboardCheck },
    { key: "supplier_documents_review", label: "Review dokumen", href: "/suppliers", icon: FileClock },
    { key: "orders_open", label: "Pesanan terbuka", href: "/inventory-orders", icon: ClipboardList },
    { key: "integrations", label: "Integrasi & rekonsiliasi", href: "/integrations", icon: Activity },
    { key: "payment_reviews", label: "Review pembayaran", href: "/inventory-orders", icon: CreditCard },
    { key: "returns_open", label: "Retur & refund", href: "/inventory-orders", icon: RotateCcw },
  ];

  return <main className="min-h-screen bg-[var(--color-canvas)]">
    <header className="border-b border-[var(--color-border)] bg-white">
      <div className="mx-auto flex min-h-[72px] max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link href="/admin" className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-primary)] text-white"><Wrench size={21}/></span>
          <span><strong className="block text-lg font-extrabold">OtoClinic</strong><span className="block text-[10px] font-bold uppercase tracking-[.15em] text-slate-500">Super Admin Control Plane</span></span>
        </Link>
        <div className="flex items-center gap-2">
          {signedIn && <span className="hidden max-w-48 truncate text-xs text-slate-500 sm:block">{email}</span>}
          <button onClick={() => void load()} disabled={loading} className="flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-xs font-bold hover:bg-slate-50 disabled:opacity-50"><RefreshCw size={14}/> Perbarui</button>
          {signedIn && <button onClick={() => void signOut()} className="flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-xs font-bold hover:bg-slate-50"><LogOut size={14}/> Keluar</button>}
        </div>
      </div>
    </header>
    <nav aria-label="Navigasi operasional" className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 py-3 sm:px-6">
        {[["Ringkasan","/admin"],["Katalog & fitment","/catalog"],["Supplier","/suppliers"],["Inventori & pesanan","/inventory-orders"],["Pengguna","/users"],["Audit log","/audit"]].map(([label,href])=><Link key={href} href={href} className={"inline-flex min-h-10 shrink-0 items-center rounded-xl border px-3 text-xs font-bold transition "+(href==="/admin"?"border-orange-200 bg-orange-50 text-[var(--color-primary)]":"border-slate-200 text-slate-600 hover:border-orange-200 hover:bg-orange-50/50")}>{label}</Link>)}
      </div>
    </nav>
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div><p className="text-xs font-extrabold uppercase tracking-[.18em] text-[var(--color-primary)]">Operasional</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight text-[var(--color-ink)]">Ringkasan operasional</h1><p className="mt-2 text-sm text-slate-500">Metrik live dihitung melalui FastAPI dengan akses sesuai role dan kebijakan database.</p></div>
        {authorized && overview && <span className="flex w-fit items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-800"><ShieldCheck size={14}/> {roleLabels[overview.role] ?? overview.role}</span>}
      </div>

      {loading ? <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500">Memeriksa sesi dan memuat data operasional…</div>
      : !signedIn ? <section className="mt-8 max-w-xl rounded-2xl border border-slate-200 bg-white p-6 sm:p-8"><ShieldCheck className="text-[var(--color-primary)]" size={28}/><h2 className="mt-4 text-xl font-extrabold">Masuk diperlukan</h2><p className="mt-2 text-sm leading-6 text-slate-500">Dashboard hanya tersedia bagi akun aktif dengan role operasional. Masuk menggunakan akun yang telah diprovisikan administrator.</p><Link href="/login" className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 text-sm font-bold text-white">Masuk ke Admin <ArrowRight size={16}/></Link></section>
      : !authorized ? <div role="alert" className="mt-8 flex max-w-2xl gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900"><AlertCircle className="shrink-0" size={20}/><div><p className="font-bold">Akses belum diberikan</p><p className="mt-1">{error || "Akun tidak memiliki izin operasional."}</p></div></div>
      : overview && <>
        {error && <div role="alert" className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div>}
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {primaryTiles.filter(t => overview.metrics[t.key]?.available).map(t => {
            const Icon = t.icon;
            return <article key={t.key} className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-50 text-[var(--color-primary)]"><Icon size={20}/></span><span className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Live</span></div>
              <p className="mt-5 text-xs font-semibold text-slate-500">{t.label}</p><p className="mt-1 text-3xl font-extrabold tabular-nums">{number(overview.metrics[t.key].value ?? 0)}</p><p className="mt-2 text-xs text-slate-400">{t.note}</p>
            </article>;
          })}
        </div>

        <section className="mt-7 rounded-2xl border border-slate-200 bg-white">
          <div className="flex flex-col justify-between gap-2 border-b border-slate-100 p-5 sm:flex-row sm:items-center sm:px-6"><div><h2 className="font-extrabold">Antrean lintas domain</h2><p className="mt-1 text-xs text-slate-500">Jumlah item pada antrean yang dapat diakses role Anda. Nilai nol berarti query live tidak menemukan item.</p></div><span className="text-xs text-slate-400">Diperbarui {new Date(overview.generated_at).toLocaleString("id-ID")}</span></div>
          <div className="grid gap-0 sm:grid-cols-2 xl:grid-cols-4">
            {queues.filter(q => overview.metrics[q.key]?.available).map(q => {
              const Icon = q.icon; const value = overview.metrics[q.key].value ?? 0;
              return <Link key={q.key} href={q.href} className="flex min-h-24 items-center gap-3 border-b border-slate-100 p-4 hover:bg-slate-50 sm:border-r"><span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-700"><Icon size={18}/></span><span className="min-w-0 flex-1"><span className="block text-sm font-semibold">{q.label}</span><span className="mt-1 block text-xs text-slate-500">{value === 0 ? "Tidak ada item tertunda" : "Perlu perhatian operasional"}</span></span><strong className={"text-xl tabular-nums " + (value > 0 ? "text-amber-700" : "text-slate-700")}>{number(value)}</strong></Link>;
            })}
          </div>
        </section>

        <section className="mt-7 grid gap-4 lg:grid-cols-[1.4fr_.6fr]">
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <div className="flex items-center justify-between border-b border-slate-100 p-5 sm:px-6"><div><h2 className="font-extrabold">Produk terbaru</h2><p className="mt-1 text-xs text-slate-500">Data yang dikembalikan API untuk role Anda.</p></div><span className="flex items-center gap-2 text-xs text-slate-500"><ClipboardList size={15}/>{overview.latest_products.length} baris</span></div>
            {overview.latest_products.length === 0 ? <div className="p-8 text-center"><Package size={28} className="mx-auto text-slate-300"/><p className="mt-3 font-bold">Belum ada data produk</p><p className="mt-1 text-sm text-slate-500">Tidak ada data contoh yang dibuat otomatis.</p></div> : <div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500"><tr>{["SKU","Produk","Kondisi","Harga","Status"].map(x=><th key={x} className="px-4 py-3 font-bold">{x}</th>)}</tr></thead><tbody>{overview.latest_products.map(p=><tr key={p.id} className="border-t border-slate-100 text-xs"><td className="px-4 py-4 font-mono">{p.sku ?? "—"}</td><td className="px-4 py-4 font-bold">{p.name}</td><td className="px-4 py-4">{p.condition}</td><td className="px-4 py-4 font-bold">{money(p.retail_price)}</td><td className="px-4 py-4"><span className="rounded-full bg-slate-100 px-2.5 py-1 font-bold">{statusLabels[p.status] ?? p.status}</span></td></tr>)}</tbody></table></div>}
          </div>
          <aside className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6"><h2 className="font-extrabold">Akses cepat</h2><div className="mt-4 space-y-2">
            <Link href="/catalog" className="flex min-h-11 items-center justify-between rounded-xl border border-slate-200 px-3 text-sm font-semibold hover:bg-slate-50">Katalog & fitment <ArrowRight size={15}/></Link>
            <Link href="/suppliers" className="flex min-h-11 items-center justify-between rounded-xl border border-slate-200 px-3 text-sm font-semibold hover:bg-slate-50">Supplier & sourcing <ArrowRight size={15}/></Link>
            <Link href="/inventory-orders" className="flex min-h-11 items-center justify-between rounded-xl border border-slate-200 px-3 text-sm font-semibold hover:bg-slate-50">Inventori & pesanan <ArrowRight size={15}/></Link>
            {overview.role === "admin" && <><Link href="/users" className="flex min-h-11 items-center justify-between rounded-xl border border-slate-200 px-3 text-sm font-semibold hover:bg-slate-50"><span className="flex items-center gap-2"><Users size={15}/> Role & pengguna</span><ArrowRight size={15}/></Link><Link href="/audit" className="flex min-h-11 items-center justify-between rounded-xl border border-slate-200 px-3 text-sm font-semibold hover:bg-slate-50"><span className="flex items-center gap-2"><Activity size={15}/> Audit explorer</span><ArrowRight size={15}/></Link></>}
          </div><p className="mt-5 text-xs leading-5 text-slate-400">Mutasi sensitif diproses oleh FastAPI dan database. Role pengguna dan audit trail hanya tersedia untuk administrator aktif.</p></aside>
        </section>
      </>}
      {error && !loading && !authorized && signedIn && <p className="mt-4 text-sm text-rose-700">{error}</p>}
    </div>
  </main>;
}
