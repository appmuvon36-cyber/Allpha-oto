"use client";
import Link from "next/link";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, LoaderCircle, ShieldCheck, Wrench } from "lucide-react";
import { getSupabaseBrowserClient } from "@/lib/supabase";

export default function LoginPage() {
  const router=useRouter();
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [info,setInfo]=useState("");
  async function submit(e:FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(""); setInfo("");
    const supabase=getSupabaseBrowserClient();
    if(!supabase){setError("Koneksi Supabase belum dikonfigurasi di environment aplikasi.");return;}
    setBusy(true);
    const {error:signInError}=await supabase.auth.signInWithPassword({email:email.trim(),password});
    setBusy(false);
    if(signInError){setError("Login gagal. Periksa email dan password atau status akun.");return;}
    setInfo("Login berhasil. Memeriksa akses operasional…");
    router.replace("/admin");
  }
  return <main className="flex min-h-screen items-center justify-center bg-[var(--color-canvas)] px-4 py-10"><div className="w-full max-w-md"><Link href="/" className="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900"><ArrowLeft size={16}/> Kembali ke OtoClinic</Link><section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"><div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[var(--color-primary)] text-white"><Wrench size={24}/></div><h1 className="mt-5 text-2xl font-extrabold">Masuk ke OtoClinic</h1><p className="mt-2 text-sm leading-6 text-slate-500">Akses dashboard operasional menggunakan akun Supabase yang sudah terdaftar. Role operasional tetap diperiksa di halaman admin.</p><form onSubmit={submit} className="mt-7 space-y-4"><label className="block text-sm font-bold">Email<input required type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3 font-normal outline-none focus:border-[var(--color-primary)]" placeholder="nama@perusahaan.id"/></label><label className="block text-sm font-bold">Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3 font-normal outline-none focus:border-[var(--color-primary)]" placeholder="Masukkan password"/></label><button disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 py-3 font-bold text-white disabled:opacity-60">{busy&&<LoaderCircle className="animate-spin" size={17}/>}Masuk</button></form>{error&&<p role="alert" className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}{info&&<p role="status" className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{info}</p>}<p className="mt-5 flex gap-2 text-xs leading-5 text-slate-400"><ShieldCheck className="shrink-0" size={15}/> Tidak ada pendaftaran admin publik. Akun dan role harus disiapkan oleh pengelola sistem.</p></section><p className="mt-5 text-center text-xs text-slate-400">OtoClinic · Akses terbatas untuk personel berwenang</p></div></main>;
}
