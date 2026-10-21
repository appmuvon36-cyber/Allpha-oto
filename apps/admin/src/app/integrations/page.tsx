"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Activity, RefreshCw, RotateCcw, Send, ShieldCheck, AlertTriangle, CheckCircle2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
type Provider = { configured: boolean; mode: string };
type Status = { providers: Record<string, Provider>; worker: { internal_secret_configured: boolean; in_process_worker_enabled: boolean }; capabilities: Record<string, boolean> };
type Outbox = { id: string; event_key: string; provider: string; event_type: string; correlation_id: string; aggregate_type: string; aggregate_id: string | null; status: string; provider_delivery_status: string | null; attempt_count: number; max_attempts: number; next_attempt_at: string; last_error_code: string | null; last_error_at: string | null; delivered_at: string | null; provider_accepted_at: string | null; provider_message_id: string | null; created_at: string; updated_at: string };
type Reconciliation = { id: string; provider: string; run_type: string; status: string; correlation_id: string; started_at: string; completed_at: string | null; scanned_count: number; matched_count: number; mismatch_count: number; failed_count: number; summary: Record<string, unknown> };
const providerLabels: Record<string, string> = { rajaongkir_payment: "RajaOngkir Payment", rajaongkir_shipping: "RajaOngkir Shipping", whatsapp_cloud: "WhatsApp Cloud API" };
const statusLabels: Record<string, string> = { pending: "Menunggu", processing: "Diproses", retry: "Menunggu retry", provider_accepted: "Diterima API provider", dead_letter: "Dead-letter", completed: "Selesai", partial: "Sebagian", failed: "Gagal", running: "Berjalan" };

export default function IntegrationsPage() {
  const router = useRouter();
  const supabase = getSupabaseBrowserClient();
  const [token, setToken] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [outbox, setOutbox] = useState<Outbox[]>([]);
  const [runs, setRuns] = useState<Reconciliation[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const api = useCallback(async (path: string, init: RequestInit = {}) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", "Bearer " + token);
    headers.set("Accept", "application/json");
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    const response = await fetch(API + path, { ...init, headers, cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Permintaan gagal (HTTP " + response.status + ").");
    return body;
  }, [token]);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    if (!supabase) { setError("Autentikasi Supabase belum dikonfigurasi."); setLoading(false); return; }
    try {
      const { data: { session }, error: authError } = await supabase.auth.getSession();
      if (authError) throw new Error("Sesi tidak dapat diperiksa.");
      if (!session?.access_token) { router.replace("/login"); return; }
      setToken(session.access_token);
      const profile = await supabase.from("user_profiles").select("role,is_active").eq("id", session.user.id).maybeSingle();
      if (profile.error || !profile.data?.is_active || !["admin", "order_manager"].includes(profile.data.role ?? "")) {
        throw new Error("Halaman integrasi memerlukan role admin atau order_manager aktif.");
      }
      setRole(profile.data.role);
      const headers = { Authorization: "Bearer " + session.access_token, Accept: "application/json" };
      const results = await Promise.all([
        fetch(API + "/v1/admin/integrations/status", { headers, cache: "no-store" }),
        fetch(API + "/v1/admin/integrations/outbox?limit=50&offset=0", { headers, cache: "no-store" }),
        fetch(API + "/v1/admin/integrations/reconciliations?limit=20&offset=0", { headers, cache: "no-store" }),
      ]);
      const bodies = await Promise.all(results.map(async r => ({ ok: r.ok, status: r.status, body: await r.json().catch(() => ({})) })));
      const failed = bodies.find(x => !x.ok);
      if (failed) throw new Error("Data integrasi tidak dapat dimuat (HTTP " + failed.status + ").");
      setStatus(bodies[0].body as Status);
      setOutbox((bodies[1].body.items ?? []) as Outbox[]);
      setRuns((bodies[2].body.items ?? []) as Reconciliation[]);
    } catch (e) { setError(e instanceof Error ? e.message : "Data integrasi tidak dapat dimuat."); }
    finally { setLoading(false); }
  }, [router, supabase]);

  useEffect(() => { void load(); }, [load]);

  async function runAction(action: "dispatch" | "reconcile" | "retry", id?: string) {
    setBusy(action + (id ?? "")); setError(""); setNotice("");
    try {
      const path = action === "dispatch" ? "/v1/admin/integrations/dispatch?limit=10"
        : action === "reconcile" ? "/v1/admin/integrations/reconcile-payments?limit=25"
        : "/v1/admin/integrations/outbox/" + id + "/retry";
      const response = await api(path, {
        method: "POST",
        headers: action === "retry" ? { "Idempotency-Key": crypto.randomUUID() } : { "X-Request-ID": crypto.randomUUID() },
        ...(action === "retry" ? {} : { body: "{}" }),
      });
      if (action === "dispatch") setNotice("Pemrosesan selesai: " + (response.delivered ?? 0) + " terkirim, " + (response.retry_scheduled ?? 0) + " dijadwalkan ulang, " + (response.dead_lettered ?? 0) + " masuk dead-letter.");
      else if (action === "reconcile") setNotice("Rekonsiliasi " + response.status + ": " + response.scanned + " diperiksa, " + response.matched + " cocok, " + response.mismatched + " tidak cocok, " + response.failed + " gagal.");
      else setNotice("Item outbox dikembalikan ke antrean. Pengiriman belum terjadi sampai worker memprosesnya.");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Aksi integrasi gagal."); }
    finally { setBusy(""); }
  }

  const pending = outbox.filter(x => ["pending", "retry", "processing"].includes(x.status)).length;
  const dead = outbox.filter(x => x.status === "dead_letter").length;

  return <main className="min-h-screen bg-[var(--color-canvas)]">
    <header className="border-b border-[var(--color-border)] bg-white"><div className="mx-auto flex min-h-[68px] max-w-7xl items-center justify-between px-4 sm:px-6"><Link href="/admin" className="inline-flex items-center gap-2 text-sm font-bold text-slate-600"><ArrowLeft size={16}/> Dashboard</Link><span className="inline-flex items-center gap-2 text-xs font-bold text-slate-500"><ShieldCheck size={15}/> Admin / Order Manager</span></div></header>
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-xs font-extrabold uppercase tracking-[.18em] text-[var(--color-primary)]">EC-08 · Reliability</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight">Integrasi & rekonsiliasi</h1><p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">Status provider, outbox, retry, dead-letter, korelasi, dan hasil rekonsiliasi. Halaman tidak menampilkan payload pesan atau kredensial.</p></div><button onClick={() => void load()} disabled={loading || !!busy} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold disabled:opacity-50"><RefreshCw size={15}/> Muat ulang</button></div>
      {error && <p role="alert" className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
      {notice && <p role="status" className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</p>}
      <section className="mt-6 grid gap-3 sm:grid-cols-3">
        <article className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-xs font-bold text-slate-500">Outbox aktif · 50 terbaru</p><p className="mt-2 text-3xl font-extrabold tabular-nums">{pending}</p><p className="mt-1 text-xs text-slate-500">Menunggu, retry, atau lease sedang diproses</p></article>
        <article className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-xs font-bold text-slate-500">Dead-letter · 50 terbaru</p><p className="mt-2 text-3xl font-extrabold tabular-nums">{dead}</p><p className="mt-1 text-xs text-slate-500">Perlu inspeksi dan tindakan operator</p></article>
        <article className="rounded-2xl border border-slate-200 bg-white p-5"><p className="text-xs font-bold text-slate-500">Role sesi</p><p className="mt-2 text-xl font-extrabold">{role === "admin" ? "Administrator" : "Manajer pesanan"}</p><p className="mt-1 text-xs text-slate-500">Izin final tetap diperiksa oleh FastAPI</p></article>
      </section>
      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center"><div><h2 className="text-lg font-extrabold">Kesiapan provider</h2><p className="mt-1 text-sm text-slate-500">Hanya status konfigurasi; nilai rahasia tidak pernah dikirim ke browser.</p></div><div className="flex flex-wrap gap-2"><button disabled={!!busy || loading} onClick={() => void runAction("dispatch")} className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-[var(--color-primary)] px-3 text-sm font-bold text-white disabled:opacity-50"><Send size={15}/>{busy === "dispatch" ? "Memproses…" : "Proses outbox"}</button><button disabled={!!busy || loading} onClick={() => void runAction("reconcile")} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-slate-200 px-3 text-sm font-bold disabled:opacity-50"><RotateCcw size={15}/>{busy === "reconcile" ? "Rekonsiliasi…" : "Rekonsiliasi pembayaran"}</button></div></div>
        {loading ? <p className="mt-5 text-sm text-slate-500">Memuat status integrasi…</p> : <div className="mt-5 grid gap-3 md:grid-cols-3">{Object.entries(status?.providers ?? {}).map(([key, provider]) => <article key={key} className="rounded-xl border border-slate-200 p-4"><div className="flex items-start justify-between gap-2"><h3 className="font-bold">{providerLabels[key] ?? key}</h3>{provider.configured ? <CheckCircle2 size={18} className="text-emerald-700"/> : <AlertTriangle size={18} className="text-amber-600"/>}</div><p className={"mt-2 text-sm font-bold " + (provider.configured ? "text-emerald-700" : "text-amber-700")}>{provider.configured ? "Dikonfigurasi" : "Nonaktif / belum lengkap"}</p><p className="mt-1 text-xs text-slate-500">Mode: {provider.mode}</p></article>)}</div>}
        {status && !status.worker.internal_secret_configured && !status.worker.in_process_worker_enabled && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-xs leading-5 text-amber-800">Worker otomatis akan aktif di dalam FastAPI saat kredensial WhatsApp Cloud API lengkap. Tanpa kredensial, antrean tetap aman; pemanggilan worker eksternal memerlukan secret dan scheduler.</p>}
      </section>
      <section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 p-5"><h2 className="font-extrabold">Integration outbox</h2><p className="mt-1 text-xs text-slate-500">50 item terbaru · correlation ID dipakai untuk menelusuri satu operasi lintas layanan</p></div>
        {loading ? <p className="p-8 text-sm text-slate-500">Memuat antrean…</p> : outbox.length === 0 ? <div className="p-10 text-center"><Activity size={30} className="mx-auto text-slate-300"/><h3 className="mt-3 font-bold">Antrean masih kosong</h3><p className="mt-1 text-sm text-slate-500">Belum ada notifikasi WhatsApp yang dimasukkan ke outbox. Tidak ada data contoh yang dibuat.</p></div> : <div className="overflow-x-auto"><table className="w-full min-w-[1000px] text-left"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500"><tr>{["Dibuat","Provider","Status","Percobaan","Korelasi","Kesalahan terakhir","Aksi"].map(x=><th key={x} className="px-4 py-3 font-bold">{x}</th>)}</tr></thead><tbody>{outbox.map(item=><tr key={item.id} className="border-t border-slate-100 align-top text-xs"><td className="whitespace-nowrap px-4 py-4 text-slate-500">{new Date(item.created_at).toLocaleString("id-ID")}</td><td className="px-4 py-4 font-bold">{providerLabels[item.provider]??item.provider}<span className="mt-1 block font-mono text-[10px] text-slate-400">{item.event_type}</span></td><td className="px-4 py-4"><span className={"rounded-full px-2 py-1 font-bold " + (item.status === "dead_letter" ? "bg-rose-50 text-rose-700" : item.status === "delivered" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700")}>{statusLabels[item.status]??item.status}</span>{item.provider_delivery_status && <span className="mt-2 block text-[10px] text-slate-500">Status pesan: {item.provider_delivery_status}</span>}</td><td className="px-4 py-4 tabular-nums">{item.attempt_count}/{item.max_attempts}<span className="mt-1 block text-[10px] text-slate-400">{item.next_attempt_at ? new Date(item.next_attempt_at).toLocaleString("id-ID") : "—"}</span></td><td className="max-w-48 break-all px-4 py-4 font-mono">{item.correlation_id}<span className="mt-1 block text-[10px] text-slate-400">{item.aggregate_id ? "Order " + item.aggregate_id.slice(-8) : item.aggregate_type}</span></td><td className="px-4 py-4 font-mono text-rose-700">{item.last_error_code??"—"}</td><td className="px-4 py-4">{role === "admin" && (["dead_letter","retry"].includes(item.status) || (item.status === "provider_accepted" && item.provider_delivery_status === "failed")) && <button disabled={!!busy} onClick={() => void runAction("retry",item.id)} className="min-h-9 rounded-lg border border-slate-200 px-3 font-bold disabled:opacity-50">{busy === "retry"+item.id ? "Memproses…" : "Masukkan ulang"}</button>}</td></tr>)}</tbody></table></div>}
      </section>
      <section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white"><div className="border-b border-slate-100 p-5"><h2 className="font-extrabold">Riwayat rekonsiliasi</h2><p className="mt-1 text-xs text-slate-500">Hasil scan payment intents yang masih pending/challenge; tidak mengubah transaksi jika nominal provider tidak cocok.</p></div>{loading ? <p className="p-8 text-sm text-slate-500">Memuat riwayat…</p> : runs.length === 0 ? <p className="p-8 text-sm text-slate-500">Belum ada proses rekonsiliasi yang tercatat.</p> : <div className="overflow-x-auto"><table className="w-full min-w-[780px] text-left"><thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-500"><tr>{["Waktu","Provider","Status","Diperiksa","Cocok","Mismatch","Gagal","Correlation ID"].map(x=><th key={x} className="px-4 py-3 font-bold">{x}</th>)}</tr></thead><tbody>{runs.map(run=><tr key={run.id} className="border-t border-slate-100 text-xs"><td className="whitespace-nowrap px-4 py-4">{new Date(run.started_at).toLocaleString("id-ID")}</td><td className="px-4 py-4">{providerLabels[run.provider]??run.provider}</td><td className="px-4 py-4 font-bold">{statusLabels[run.status]??run.status}</td><td className="px-4 py-4 tabular-nums">{run.scanned_count}</td><td className="px-4 py-4 tabular-nums">{run.matched_count}</td><td className="px-4 py-4 tabular-nums">{run.mismatch_count}</td><td className="px-4 py-4 tabular-nums">{run.failed_count}</td><td className="max-w-44 break-all px-4 py-4 font-mono">{run.correlation_id}</td></tr>)}</tbody></table></div>}</section>
      <p className="mt-5 text-xs leading-5 text-slate-500">Status “Diterima API provider” hanya berarti API mengembalikan ID pesan. Status sent/delivered/read/failed diperbarui dari webhook Meta yang tanda tangannya tervalidasi.</p>
    </div>
  </main>;
}
