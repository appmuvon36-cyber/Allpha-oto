"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, BellRing, ShieldCheck } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
const CONSENT_VERSION = "whatsapp-order-status-v1";
type Preference = { whatsapp_opt_in: boolean; consent_version: string | null; consented_at: string | null; revoked_at: string | null };

export default function NotificationPreferencesPage() {
  const supabase = getSupabaseBrowserClient();
  const router = useRouter();
  const [token, setToken] = useState("");
  const [preference, setPreference] = useState<Preference | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async (accessToken: string) => {
    const response = await fetch(API + "/v1/notifications/whatsapp-consent", { headers: { Authorization: "Bearer " + accessToken, Accept: "application/json" }, cache: "no-store" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Preferensi notifikasi tidak dapat dimuat.");
    setPreference(body.preference as Preference);
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      if (!supabase) { setError("Autentikasi belum dikonfigurasi."); setLoading(false); return; }
      const { data: { session }, error: authError } = await supabase.auth.getSession();
      if (!active) return;
      if (authError || !session?.access_token) { setError("Masuk ke akun pelanggan untuk mengatur preferensi."); setLoading(false); return; }
      setToken(session.access_token);
      try { await load(session.access_token); }
      catch (e) { if (active) setError(e instanceof Error ? e.message : "Preferensi tidak dapat dimuat."); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [load, supabase]);

  async function save(optIn: boolean) {
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(API + "/v1/notifications/whatsapp-consent", {
        method: "POST",
        headers: { Authorization: "Bearer " + token, "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ opt_in: optIn, consent_version: optIn ? CONSENT_VERSION : undefined }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Preferensi tidak dapat disimpan.");
      setPreference(body.preference as Preference);
      setNotice(optIn ? "Persetujuan notifikasi WhatsApp tercatat." : "Persetujuan WhatsApp telah dicabut.");
    } catch (e) { setError(e instanceof Error ? e.message : "Preferensi tidak dapat disimpan."); }
    finally { setBusy(false); }
  }

  return <main className="min-h-screen bg-[var(--color-canvas)] px-4 py-8 sm:py-12"><div className="mx-auto max-w-2xl">
    <Link href="/account" className="inline-flex items-center gap-2 text-sm font-bold text-slate-600"><ArrowLeft size={16}/> Akun pelanggan</Link>
    <div className="mt-5 flex items-center gap-3"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-orange-100 text-orange-700"><BellRing size={23}/></span><div><h1 className="text-2xl font-extrabold">Preferensi notifikasi</h1><p className="text-sm text-slate-500">Kelola persetujuan pesan status pesanan via WhatsApp.</p></div></div>
    {error && <p role="alert" className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
    {notice && <p role="status" className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</p>}
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
      {loading ? <p role="status" className="text-sm text-slate-500">Memuat preferensi…</p> : !token ? <div><p className="text-sm leading-6 text-slate-600">Anda perlu masuk sebelum mengatur persetujuan.</p><Link href="/account" className="mt-4 inline-flex min-h-11 items-center rounded-xl bg-[var(--color-primary)] px-4 font-bold text-white">Masuk ke akun</Link></div> : <>
        <div className="flex items-start gap-3"><ShieldCheck className="mt-1 shrink-0 text-emerald-700" size={21}/><div><h2 className="font-extrabold">Notifikasi status pesanan</h2><p className="mt-2 text-sm leading-6 text-slate-600">Jika Anda setuju, OtoClinic dapat mengirim pesan WhatsApp yang berkaitan dengan status pesanan ke nomor telepon profil Anda. Anda dapat mencabut persetujuan kapan saja. Persetujuan ini tidak mengaktifkan provider yang belum dikonfigurasi dan tidak menjamin pesan terkirim.</p></div></div>
        <div className="mt-5 rounded-xl border border-slate-200 p-4"><p className="text-sm font-bold">Status persetujuan: <span className={preference?.whatsapp_opt_in ? "text-emerald-700" : "text-slate-500"}>{preference?.whatsapp_opt_in ? "Aktif" : "Tidak aktif"}</span></p>{preference?.consented_at && <p className="mt-1 text-xs text-slate-500">Diberikan: {new Date(preference.consented_at).toLocaleString("id-ID")}</p>}{preference?.revoked_at && !preference.whatsapp_opt_in && <p className="mt-1 text-xs text-slate-500">Dicabut: {new Date(preference.revoked_at).toLocaleString("id-ID")}</p>}</div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">{!preference?.whatsapp_opt_in ? <button disabled={busy} onClick={() => void save(true)} className="min-h-11 rounded-xl bg-[var(--color-primary)] px-4 font-extrabold text-white disabled:opacity-50">{busy ? "Menyimpan…" : "Saya setuju menerima notifikasi WhatsApp"}</button> : <button disabled={busy} onClick={() => void save(false)} className="min-h-11 rounded-xl border border-rose-200 px-4 font-bold text-rose-700 disabled:opacity-50">{busy ? "Menyimpan…" : "Cabut persetujuan"}</button>}</div>
      </>}
    </section>
  </div></main>;
}
