"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, FileUp, ShieldAlert, Upload } from "lucide-react";
import Link from "next/link";
import { getSupabaseBrowserClient } from "@/lib/supabase";

type Row = Record<string, string>;
type Mapping = { title: string; category: string; source: string; price: string; condition: string; brand: string; partNumber: string; sku: string };
const defaults: Mapping = { title: "product_title_source", category: "part_category", source: "source_url", price: "price_normalized_idr", condition: "condition_raw", brand: "brand_part_number", partNumber: "brand_part_number", sku: "internal_product_key" };
function parseCsv(text: string): Row[] {
  const records: string[][] = []; let row: string[] = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"' && quoted && text[i + 1] === '"') { cell += '"'; i++; }
    else if (ch === '"') quoted = !quoted;
    else if (ch === "," && !quoted) { row.push(cell); cell = ""; }
    else if ((ch === "\n" || ch === "\r") && !quoted) { if (ch === "\r" && text[i + 1] === "\n") i++; row.push(cell); if (row.some(v => v.trim())) records.push(row); row = []; cell = ""; }
    else cell += ch;
  }
  if (cell.length || row.length) { row.push(cell); if (row.some(v => v.trim())) records.push(row); }
  if (records.length < 2) return [];
  const headers = records[0].map(h => h.trim().replace(/^\uFEFF/, ""));
  return records.slice(1).map(values => Object.fromEntries(headers.map((h, i) => [h, (values[i] ?? "").trim()])));
}
const slugify = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 100);
const conditionValue = (s: string) => { const x = s.toLowerCase(); if (x.includes("bekas") || x.includes("used")) return "used"; if (x.includes("oem")) return "new_oem"; if (x.includes("rekondisi")) return "refurbished"; return "new_aftermarket"; };
function canonicalProductUrl(value: string) { try { const u = new URL(value); return ["http:", "https:"].includes(u.protocol) && !/(search|category|kategori|shop|store|keyword|q=)/i.test(u.pathname + u.search) && u.hostname.includes("."); } catch { return false; } }

export default function CatalogImportPage() {
  const router = useRouter();
  const [fileName, setFileName] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<Mapping>(defaults);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const report = useMemo(() => {
    const seen = new Set<string>();
    return rows.map((row, i) => {
      const title = row[mapping.title] ?? "", category = row[mapping.category] ?? "", source = row[mapping.source] ?? "";
      const key = (row[mapping.sku] || title).toLowerCase().trim();
      const duplicate = !!key && seen.has(key); if (key) seen.add(key);
      const issues: string[] = [];
      if (!title) issues.push("Nama produk kosong");
      if (!category) issues.push("Kategori kosong");
      if (!canonicalProductUrl(source)) issues.push("URL bukan halaman produk individual yang dapat dikenali");
      if (duplicate) issues.push("Duplikat di dalam file");
      const rightsWarning = !!row.photo_rights_status && !["user_owned","permission_granted","licensed","public_domain"].includes(row.photo_rights_status);
      const rawPrice = row[mapping.price] ?? "";
      const price = rawPrice ? Number(rawPrice.replace(/[^0-9.-]/g, "")) : null;
      if (rawPrice && (!Number.isFinite(price) || Number(price) <= 0)) issues.push("Harga tidak valid");
      return { row, index: i + 1, title, source, category, issues, rightsWarning, price, duplicate, eligible: issues.length === 0 };
    });
  }, [rows, mapping]);
  const importable = report.filter(r => r.eligible);
  async function readFile(file?: File) {
    setError(""); setNotice(""); setRows([]); setHeaders([]);
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) { setError("Pilih berkas .csv. Format Excel harus diekspor menjadi CSV UTF-8 terlebih dahulu."); return; }
    if (file.size > 10 * 1024 * 1024) { setError("Ukuran CSV maksimum 10 MB."); return; }
    const parsed = parseCsv(await file.text());
    if (!parsed.length) { setError("CSV kosong atau format header/baris tidak valid."); return; }
    const cols = Object.keys(parsed[0]); setFileName(file.name); setRows(parsed); setHeaders(cols);
    setMapping({
      title: cols.find(x => /product_title_source|product_title|nama_produk|name/i.test(x)) ?? cols[0],
      category: cols.find(x => /part_category|category|kategori/i.test(x)) ?? "",
      source: cols.find(x => /source_url|product_url|url_sumber/i.test(x)) ?? "",
      price: cols.find(x => /price_normalized_idr|price_min_idr|harga/i.test(x)) ?? "",
      condition: cols.find(x => /condition_raw|condition|kondisi/i.test(x)) ?? "",
      brand: cols.find(x => /^brand$/i.test(x)) ?? "",
      partNumber: cols.find(x => /part_number|nomor_part/i.test(x)) ?? "",
      sku: cols.find(x => /internal_product_key|sku/i.test(x)) ?? "",
    });
  }
  async function importDrafts() {
    setBusy(true); setError(""); setNotice(""); setProgress({ done: 0, total: importable.length });
    try {
      const supabase = getSupabaseBrowserClient();
      if (!supabase) throw new Error("Konfigurasi Supabase Admin tidak tersedia.");
      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.access_token) { router.replace("/login"); throw new Error("Sesi Admin berakhir. Silakan login ulang."); }
      const api = process.env.NEXT_PUBLIC_API_URL || "https://otoclinic-api-production.up.railway.app";
      let success = 0; const failures: string[] = [];
      for (const item of importable) {
        const row = item.row;
        const productName = item.title.trim();
        const rawSku = row[mapping.sku] || "";
        const sku = rawSku ? rawSku.slice(0, 120) : null;
        const payload = {
          sku, slug: slugify(productName) + "-" + (item.index.toString().padStart(3, "0")),
          name: productName, description: "Kandidat katalog diimpor dari CSV; verifikasi pemasok, kondisi, harga, dan fitment sebelum publikasi.",
          brand: row[mapping.brand] || null, part_number: row[mapping.partNumber] || null,
          category: item.category, condition: conditionValue(row[mapping.condition] || ""),
          condition_grade: null, package_quantity: null, warranty_days: 0, currency: "IDR",
          retail_price: item.price, status: "draft", source_rights_evidence: {
            source_url: item.source, import_file: fileName, source_row: item.index,
            evidence_notes: row.evidence_notes || "", confidence_source: row.confidence_source || "",
            price_stock_verified: row.price_stock_verified || "NO", fitment_verified: row.fitment_verified || "NO",
            condition_verified: row.condition_verified || "NO", photo_rights_status: row.photo_rights_status || "REFERENCE_ONLY_OR_PERMISSION_REQUIRED",
            pricing_status: row.pricing_status || "NOT_READY", imported_at: new Date().toISOString()
          },
          fitment_summary: row.vehicle_make || row.vehicle_type || null
        };
        try {
          const response = await fetch(api + "/v1/admin/catalog/mutations", {
            method: "POST", headers: { "Authorization": "Bearer " + session.access_token, "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
            body: JSON.stringify({ action: "create_product", payload })
          });
          if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || "HTTP " + response.status); }
          success++;
        } catch (e) { failures.push("Baris " + item.index + ": " + (e instanceof Error ? e.message : "gagal")); }
        setProgress({ done: success + failures.length, total: importable.length });
      }
      setNotice("Selesai: " + success + " draft dibuat; " + failures.length + " gagal. Semua item tetap draft, tidak ada publikasi otomatis.");
      if (failures.length) setError(failures.slice(0, 8).join("\n") + (failures.length > 8 ? "\nDan kegagalan lainnya; periksa laporan impor." : ""));
    } catch (e) { setError(e instanceof Error ? e.message : "Impor gagal."); }
    finally { setBusy(false); }
  }
  const field = (label: string, key: keyof Mapping) => <label className="grid gap-1 text-sm text-slate-700">{label}<select className="min-h-11 rounded-lg border border-slate-300 bg-white px-3" value={mapping[key]} onChange={e => setMapping(p => ({ ...p, [key]: e.target.value }))}><option value="">— Tidak dipetakan —</option>{headers.map(h => <option key={h} value={h}>{h}</option>)}</select></label>;
  return <main className="min-h-screen bg-slate-50 px-4 py-6 text-slate-900 md:px-8">
    <div className="mx-auto max-w-7xl space-y-6">
      <header className="flex flex-wrap items-center gap-3"><Link href="/catalog" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium"><ArrowLeft size={16}/>Kembali ke katalog</Link><div><p className="text-sm font-semibold text-orange-700">OtoClinic · Admin</p><h1 className="text-2xl font-bold md:text-3xl">Impor katalog CSV</h1></div></header>
      <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold">1. Pilih berkas</h2><p className="mt-1 text-sm text-slate-600">CSV UTF-8, maksimal 10 MB. Pratinjau dilakukan di browser; penulisan produk hanya melalui FastAPI dengan sesi Admin.</p><label className="mt-4 flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-slate-300 p-8 text-center hover:border-orange-500"><FileUp size={28}/><span className="font-semibold">{fileName || "Pilih file CSV dari perangkat"}</span><span className="text-sm text-slate-500">Klik untuk memilih file</span><input type="file" accept=".csv,text/csv" className="sr-only" onChange={e => void readFile(e.target.files?.[0])}/></label></section>
      {headers.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-lg font-semibold">2. Pemetaan kolom</h2><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{field("Nama produk *","title")}{field("Kategori *","category")}{field("URL sumber *","source")}{field("Harga IDR","price")}{field("Kondisi","condition")}{field("Merek","brand")}{field("Nomor part","partNumber")}{field("SKU / kunci internal","sku")}</div></section>}
      {report.length > 0 && <section className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">3. Pratinjau & validasi</h2><p className="mt-1 text-sm text-slate-600">Baris valid: {importable.length} · perlu perbaikan/review: {report.length - importable.length} · total: {report.length}</p></div><button disabled={busy || importable.length===0} onClick={() => void importDrafts()} className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-orange-600 px-4 font-semibold text-white disabled:opacity-50"><Upload size={16}/>{busy ? "Mengimpor " + progress.done + "/" + progress.total : "Impor " + importable.length + " draft"}</button></div>
      <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-slate-100"><tr>{["Baris","Nama produk","Kategori","Harga","URL sumber","Status validasi"].map(x=><th key={x} className="p-3 font-semibold">{x}</th>)}</tr></thead><tbody>{report.slice(0,100).map(r=><tr key={r.index} className="border-t border-slate-100 align-top"><td className="p-3">{r.index}</td><td className="p-3 font-medium">{r.title || "—"}</td><td className="p-3">{r.category || "—"}</td><td className="p-3">{r.price == null ? "Belum ada" : new Intl.NumberFormat("id-ID",{style:"currency",currency:"IDR",maximumFractionDigits:0}).format(r.price)}</td><td className="max-w-64 break-all p-3 text-slate-600">{r.source || "—"}</td><td className="p-3">{r.eligible ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 size={15}/>Dapat diimpor sebagai draft</span> : <span className="inline-flex items-center gap-1 text-amber-700"><ShieldAlert size={15}/>{r.issues.join("; ")}{r.rightsWarning ? "; hak foto perlu review sebelum publikasi" : ""}</span>}</td></tr>)}</tbody></table></div>{report.length>100 && <p className="mt-2 text-sm text-slate-500">Tabel menampilkan 100 baris pertama; validasi mencakup seluruh {report.length} baris.</p>}</section>}
      {notice && <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</p>}
      {error && <pre role="alert" className="whitespace-pre-wrap rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</pre>}
      <aside className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><strong>Catatan publikasi:</strong> data sumber, harga, stok, fitment, kondisi, dan hak foto tetap disimpan sebagai bukti. Status foto referensi atau izin yang belum ada bukan bukti hak pakai. Produk yang diimpor tetap draft; publikasi dan foto memerlukan review terpisah di katalog.</aside>
    </div>
  </main>;
}
