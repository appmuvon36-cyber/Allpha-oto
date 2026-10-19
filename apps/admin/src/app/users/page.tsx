"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, RefreshCw, Save, ShieldCheck, Users } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://otoclinic-api-production.up.railway.app";
const roleOptions = [
  { value: "customer", label: "Pelanggan" },
  { value: "supplier", label: "Pemasok" },
  { value: "catalog_editor", label: "Editor katalog" },
  { value: "inventory_manager", label: "Manajer inventori" },
  { value: "order_manager", label: "Manajer pesanan" },
  { value: "moderator", label: "Moderator" },
  { value: "admin", label: "Administrator" },
] as const;
type Role = typeof roleOptions[number]["value"];
type Profile = { id: string; display_name: string | null; role: Role; is_active: boolean; created_at: string; updated_at: string };
type Draft = { role: Role; is_active: boolean };
type Filters = { limit: number; offset: number; next_offset: number | null; items: Profile[]; count: number };

export default function AdminUsersPage() {
  const router = useRouter();
  const supabase = getSupabaseBrowserClient();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [selfId, setSelfId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [offset, setOffset] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async (requestedOffset = 0) => {
    setLoading(true); setError("");
    if (!supabase) { setError("Autentikasi Supabase belum dikonfigurasi."); setLoading(false); return; }
    try {
      const { data: { session }, error: authError } = await supabase.auth.getSession();
      if (authError) throw new Error("Sesi tidak dapat diperiksa.");
      if (!session?.access_token) { router.replace("/login"); return; }
      setSelfId(session.user.id);
      const response = await fetch(API + "/v1/admin/users?limit=50&offset=" + requestedOffset, {
        headers: { Authorization: "Bearer " + session.access_token, Accept: "application/json" }, cache: "no-store",
      });
      if (response.status === 401) { router.replace("/login"); return; }
      if (response.status === 403) throw new Error("Akses ditolak. Hanya administrator aktif yang dapat mengelola role.");
      if (!response.ok) throw new Error("Daftar pengguna tidak dapat dimuat (HTTP " + response.status + ").");
      const data = await response.json() as Filters;
      setProfiles(data.items);
      setDrafts(Object.fromEntries(data.items.map(p => [p.id, { role: p.role, is_active: p.is_active }])));
      setOffset(data.offset);
      setNextOffset(data.next_offset);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Daftar pengguna tidak dapat dimuat.");
    } finally { setLoading(false); }
  }, [router, supabase]);

  useEffect(() => { void load(0); }, [load]);

  function updateDraft(id: string, key: keyof Draft, value: string | boolean) {
    setDrafts(current => ({ ...current, [id]: { ...current[id], [key]: value } as Draft }));
  }

  async function saveProfile(profile: Profile) {
    const draft = drafts[profile.id];
    if (!draft || (draft.role === profile.role && draft.is_active === profile.is_active)) return;
    if (profile.id === selfId) { setError("Role dan status akun sendiri tidak dapat diubah dari sesi ini."); return; }
    const roleLabel = roleOptions.find(r => r.value === draft.role)?.label ?? draft.role;
    const message = "Simpan perubahan akses untuk " + (profile.display_name || profile.id) + "?\n\nRole: " + roleLabel + "\nStatus: " + (draft.is_active ? "Aktif" : "Nonaktif") + "\n\nPerubahan akan dicatat di audit log.";
    if (!window.confirm(message)) return;
    setBusyId(profile.id); setError(""); setNotice("");
    try {
      const { data: { session } } = await supabase!.auth.getSession();
      if (!session?.access_token) { router.replace("/login"); return; }
      const response = await fetch(API + "/v1/admin/users/" + encodeURIComponent(profile.id) + "/role", {
        method: "POST",
        headers: { Authorization: "Bearer " + session.access_token, "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(draft),
      });
      const body = await response.json().catch(() => ({})) as { detail?: string; result?: { profile?: Profile } };
      if (!response.ok) throw new Error(body.detail || "Perubahan role ditolak (HTTP " + response.status + ").");
      setNotice("Perubahan akses tersimpan dan tercatat pada audit log.");
      await load(offset);
      setNotice("Perubahan akses tersimpan dan tercatat pada audit log.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Perubahan akses gagal.");
    } finally { setBusyId(""); }
  }

  return <main className="min-h-screen bg-[var(--color-canvas)]">
    <header className="border-b border-[var(--color-border)] bg-white"><div className="mx-auto flex min-h-[68px] max-w-7xl items-center justify-between px-4 sm:px-6"><Link href="/admin" className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 hover:text-slate-900"><ArrowLeft size={16}/> Dashboard</Link><span className="inline-flex items-center gap-2 text-xs font-bold text-slate-500"><ShieldCheck size={15}/> Admin-only</span></div></header>
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-extrabold uppercase tracking-[.18em] text-[var(--color-primary)]">Governance</p><h1 className="mt-2 text-3xl font-extrabold tracking-tight">Pengguna & kontrol role</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">Perubahan role diproses melalui FastAPI dan RPC database, menggunakan idempotency key, guard administrator terakhir, dan audit trail.</p></div><button onClick={() => void load(offset)} disabled={loading} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold disabled:opacity-50"><RefreshCw size={15}/> Muat ulang</button></div>
      {notice && <p role="status" className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</p>}
      {error && <p role="alert" className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
      <section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 p-5"><div><h2 className="font-extrabold">Profil terdaftar</h2><p className="mt-1 text-xs text-slate-500">Tidak menampilkan email atau nomor telepon pada daftar ini.</p></div><span className="inline-flex items-center gap-2 text-xs text-slate-500"><Users size={15}/>{profiles.length} profil pada halaman ini</span></div>
        {loading ? <div className="p-8 text-sm text-slate-500">Memuat profil melalui API…</div>
        : profiles.length === 0 ? <div className="p-10 text-center"><Users size={30} className="mx-auto text-slate-300"/><h3 className="mt-3 font-bold">Belum ada profil yang dapat ditampilkan</h3><p className="mt-1 text-sm text-slate-500">Daftar ini menggunakan data live. Tidak ada akun contoh yang dibuat.</p></div>
        : <div className="divide-y divide-slate-100">{profiles.map(profile => {
          const draft = drafts[profile.id] ?? { role: profile.role, is_active: profile.is_active };
          const changed = draft.role !== profile.role || draft.is_active !== profile.is_active;
          const isSelf = profile.id === selfId;
          return <article key={profile.id} className="grid gap-4 p-4 sm:grid-cols-[minmax(0,1fr)_180px_130px_auto] sm:items-center sm:px-5">
            <div className="min-w-0"><p className="truncate font-bold">{profile.display_name || "Nama belum diatur"}</p><p className="mt-1 break-all font-mono text-[11px] text-slate-400">{profile.id}</p><p className="mt-1 text-xs text-slate-500">Diperbarui {new Date(profile.updated_at).toLocaleString("id-ID")}{isSelf ? " · Sesi saat ini" : ""}</p></div>
            <label className="block text-xs font-bold text-slate-600">Role<select aria-label={"Role " + profile.id} disabled={isSelf || busyId === profile.id} value={draft.role} onChange={e => updateDraft(profile.id, "role", e.target.value)} className="mt-2 min-h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-800 outline-none focus:border-[var(--color-primary)] disabled:bg-slate-100">{roleOptions.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}</select></label>
            <label className="flex min-h-11 items-center gap-3 text-sm font-semibold"><input type="checkbox" disabled={isSelf || busyId === profile.id} checked={draft.is_active} onChange={e => updateDraft(profile.id, "is_active", e.target.checked)} className="h-4 w-4 accent-[var(--color-primary)]"/> Akun aktif</label>
            <button disabled={isSelf || !changed || busyId === profile.id} onClick={() => void saveProfile(profile)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300">{busyId === profile.id ? <RefreshCw size={15} className="animate-spin"/> : <Save size={15}/>}Simpan</button>
          </article>;
        })}</div>}
        <div className="flex items-center justify-between border-t border-slate-100 p-4"><span className="text-xs text-slate-500">Offset {offset}</span><div className="flex gap-2"><button disabled={loading || offset === 0} onClick={() => void load(Math.max(0, offset - 50))} className="min-h-10 rounded-lg border border-slate-200 px-3 text-sm font-semibold disabled:opacity-40">Sebelumnya</button><button disabled={loading || nextOffset === null} onClick={() => nextOffset !== null && void load(nextOffset)} className="min-h-10 rounded-lg border border-slate-200 px-3 text-sm font-semibold disabled:opacity-40">Berikutnya</button></div></div>
      </section>
    </div>
  </main>;
}
