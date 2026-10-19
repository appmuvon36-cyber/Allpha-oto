"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, FileSpreadsheet, Upload } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL || "https://otoclinic-api-production.up.railway.app";
const HEADERS = ["sku", "product_id", "marketplace_listing_url", "marketplace_image_url", "alt_text"];
type Row = Record<string, string>;
type Parsed = { line: number; values: Row; errors: string[] };
type Result = { line: number; sku: string; status: "success" | "error" | "invalid"; message: string; storagePath?: string };

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"' && field.length === 0) quoted = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n") { row.push(field.replace(/\r$/, "")); rows.push(row); row = []; field = ""; }
    else field += ch;
  }
  if (quoted) throw new Error("CSV memiliki tanda kutip yang belum ditutup.");
  if (field.length || row.length) { row.push(field.replace(/\r$/, "")); rows.push(row); }
  return rows.filter((r) => r.some((v) => v.trim() !== ""));
}

function validateCsv(text: string): Parsed[] {
  const matrix = parseCsv(text);
  if (matrix.length < 2) throw new Error("CSV harus berisi header dan minimal satu baris media.");
  const headers = matrix[0].map((v) => v.trim().toLowerCase().replace(/^\uFEFF/, ""));
  const missing = HEADERS.filter((h) => !headers.includes(h));
  if (missing.length) throw new Error("Kolom wajib belum ada: " + missing.join(", "));
  if (matrix.length - 1 > 100) throw new Error("Maksimal 100 foto per batch.");
  return matrix.slice(1).map((cells, index) => {
    const values: Row = {};
    headers.forEach((h, i) => { if (h) values[h] = (cells[i] ?? "").trim(); });
    const errors: string[] = [];
    for (const key of HEADERS) if (!values[key]) errors.push(key + " wajib diisi");
    if (values.product_id && !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(values.product_id)) errors.push("product_id bukan UUID yang valid");
    try {
      if (values.marketplace_listing_url && new URL(values.marketplace_listing_url).protocol !== "https:") errors.push("listing harus memakai HTTPS");
      if (values.marketplace_image_url && new URL(values.marketplace_image_url).protocol !== "https:") errors.push("foto harus memakai HTTPS");
    } catch { errors.push("URL listing/foto tidak valid"); }
    return { line: index + 2, values, errors };
  });
}

function downloadTemplate() {
  const csv = "\uFEFF" + HEADERS.join(",") + "\r\n";
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "otoclinic-media-existing-products-template.csv"; a.click();
  URL.revokeObjectURL(url);
}

export default function CatalogMediaBatchImportPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [fileName, setFileName] = useState("");
  const [rows, setRows] = useState<Parsed[]>([]);
  const [parseError, setParseError] = useState("");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Result[]>([]);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let alive = true;
    void (async () => {
      const client = getSupabaseBrowserClient();
      if (!client) { setParseError("Supabase Auth belum dikonfigurasi."); return; }
      const { data, error } = await client.auth.getSession();
      if (error || !data.session) { router.replace("/login"); return; }
      if (!alive) return;
      const accessToken = data.session.access_token;
      const me = await fetch(API + "/v1/auth/me", { headers: { Authorization: "Bearer " + accessToken } });
      const body = await me.json().catch(() => ({}));
      if (!me.ok) { setParseError("Identitas staf tidak dapat diverifikasi melalui API."); return; }
      const role = String(body.role ?? body.profile?.role ?? "");
      if (!["admin", "catalog_editor", "moderator"].includes(role)) {
        setParseError("Akun ini tidak memiliki izin impor media katalog.");
        return;
      }
      setToken(accessToken);
    })();
    return () => { alive = false; };
  }, [router]);

  const validCount = useMemo(() => rows.filter((r) => !r.errors.length).length, [rows]);

  async function chooseFile(file: File | null) {
    setRows([]); setResults([]); setNotice(""); setParseError("");
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { setParseError("Ukuran CSV maksimal 5 MB."); return; }
    try { setRows(validateCsv(await file.text())); setFileName(file.name); }
    catch (e) { setParseError(e instanceof Error ? e.message : "CSV tidak dapat dibaca."); }
  }

  async function importMedia() {
    if (!token || !rows.length || validCount === 0 || busy) return;
    setBusy(true); setParseError(""); setNotice(""); setResults([]);
    const out: Result[] = [];
    try {
      const productResponse = await fetch(API + "/v1/admin/products", { headers: { Authorization: "Bearer " + token } });
      const productBody = await productResponse.json().catch(() => ({}));
      if (!productResponse.ok) throw new Error(productBody.detail || "Daftar produk existing tidak dapat dimuat.");
      const products: Array<{ id: string; sku: string; status: string; name?: string }> = Array.isArray(productBody.items) ? productBody.items : [];
      const byId = new Map(products.map((p) => [p.id.toLowerCase(), p]));
      const bySku = new Map(products.map((p) => [String(p.sku).toLowerCase(), p]));
      for (const row of rows) {
        const v = row.values;
        if (row.errors.length) { out.push({ line: row.line, sku: v.sku || "", status: "invalid", message: row.errors.join("; ") }); setResults([...out]); continue; }
        const byIdProduct = byId.get(v.product_id.toLowerCase());
        const bySkuProduct = bySku.get(v.sku.toLowerCase());
        if (!byIdProduct || !bySkuProduct || byIdProduct.id !== bySkuProduct.id) {
          out.push({ line: row.line, sku: v.sku, status: "error", message: "SKU dan product_id tidak cocok dengan produk existing; tidak diimpor." });
          setResults([...out]); continue;
        }
        if (!["draft", "in_review", "review"].includes(String(byIdProduct.status).toLowerCase())) {
          out.push({ line: row.line, sku: v.sku, status: "error", message: "Produk bukan draft/review; tidak diimpor." });
          setResults([...out]); continue;
        }
        try {
          const response = await fetch(API + "/v1/admin/catalog/products/" + encodeURIComponent(byIdProduct.id) + "/media/import-marketplace", {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
            body: JSON.stringify({
              image_url: v.marketplace_image_url,
              source_listing_url: v.marketplace_listing_url,
              alt_text: v.alt_text || ("Foto referensi draft " + (byIdProduct.name || v.sku))
            })
          });
          const body = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(body.detail || "API menolak impor media.");
          const storagePath = String(body.media?.storage_path || "");
          out.push({ line: row.line, sku: v.sku, status: "success", message: "Foto tersimpan; review pending; tetap privat.", storagePath });
        } catch (e) {
          out.push({ line: row.line, sku: v.sku, status: "error", message: e instanceof Error ? e.message : "Impor gagal." });
        }
        setResults([...out]);
      }
      const ok = out.filter((x) => x.status === "success").length;
      const failed = out.length - ok;
      setNotice("Selesai: " + ok + " foto berhasil diimpor, " + failed + " baris perlu ditinjau. Tidak ada produk baru yang dibuat.");
    } catch (e) {
      setParseError(e instanceof Error ? e.message : "Impor batch gagal.");
    } finally { setBusy(false); }
  }

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 p-4 md:p-8">
      <Link href="/catalog" className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-950"><ArrowLeft size={16} /> Kembali ke katalog</Link>
      <header className="space-y-2">
        <p className="text-sm font-semibold uppercase tracking-wide text-orange-600">OtoClinic · Media Katalog</p>
        <h1 className="text-2xl font-bold text-slate-950 md:text-3xl">Impor foto untuk produk existing</h1>
        <p className="max-w-3xl text-sm leading-6 text-slate-600">Unggah CSV dengan SKU dan product_id yang sudah ada. Halaman ini tidak membuat produk baru. Foto disimpan privat untuk review; status produk tidak berubah dan foto tidak dipublikasikan ke Customer Web.</p>
      </header>
      <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3"><FileSpreadsheet className="text-orange-600" /><div><h2 className="font-semibold text-slate-900">Format CSV khusus media</h2><p className="text-sm text-slate-500">Kolom: sku, product_id, marketplace_listing_url, marketplace_image_url, alt_text</p></div></div>
          <button type="button" onClick={downloadTemplate} className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"><Download size={16} /> Unduh template</button>
        </div>
        <label className="block space-y-2"><span className="text-sm font-semibold text-slate-800">Pilih CSV pemetaan media</span><input type="file" accept=".csv,text/csv" disabled={busy} onChange={(e) => void chooseFile(e.target.files?.[0] ?? null)} className="block w-full rounded-xl border border-slate-300 p-3 text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2" /></label>
        {fileName && <p className="text-sm text-slate-600">File: <strong>{fileName}</strong> · {rows.length} baris · {validCount} baris lolos pemeriksaan format</p>}
        {parseError && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{parseError}</div>}
        {notice && <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</div>}
        <button type="button" disabled={!token || !rows.length || validCount === 0 || busy} onClick={() => void importMedia()} className="inline-flex items-center gap-2 rounded-lg bg-orange-600 px-5 py-3 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"><Upload size={16} /> {busy ? "Mengimpor foto…" : "Impor foto ke produk existing"}</button>
      </section>
      {results.length > 0 && <section className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5"><h2 className="font-semibold text-slate-900">Hasil impor</h2><div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-sm"><thead><tr className="border-b border-slate-200 text-slate-500"><th className="py-2 pr-3">Baris</th><th className="py-2 pr-3">SKU</th><th className="py-2 pr-3">Status</th><th className="py-2 pr-3">Keterangan / storage_path</th></tr></thead><tbody>{results.map((r) => <tr key={r.line} className="border-b border-slate-100 align-top"><td className="py-3 pr-3">{r.line}</td><td className="py-3 pr-3 font-mono">{r.sku}</td><td className="py-3 pr-3"><span className={r.status === "success" ? "font-semibold text-emerald-700" : "font-semibold text-rose-700"}>{r.status}</span></td><td className="py-3 pr-3 break-all">{r.storagePath || r.message}</td></tr>)}</tbody></table></div></section>}
    </main>
  );
}
