# OtoClinic

**OtoClinic** adalah platform marketplace dan operasi spare part otomotif untuk Indonesia—mobil dan sepeda motor, suku cadang OEM dan aftermarket, barang bekas/copotan, rekondisi, remanufaktur, serta barang untuk kanibal part.

## Brand & repository
- Brand produk: **OtoClinic**
- Repository: `appmuvon36-cyber/Allpha-oto` (nama repository dipertahankan agar URL dan integrasi yang ada tidak rusak)
- Supabase project: `nunnugavnpaumqefmitn` (`otomarket-allpha`, region `ap-southeast-2`)
- Branch implementasi yang diminta: `main`
- Bahasa UI: Bahasa Indonesia; mata uang: IDR.

## Status awal yang teramati
Repository `main` awalnya hanya berisi README, tanpa source aplikasi atau konfigurasi build. Supabase sudah memiliki tabel bisnis di schema `public` (termasuk `user_profiles`, `vehicle_makes/models/variants`, `products`, `product_fitments`, `suppliers`, `supplier_offers`, `inventory_ledger`, dan `audit_logs`). Jangan mengganti atau membuat ulang tabel-tabel tersebut tanpa rekonsiliasi schema.

Satu advisory Supabase mengidentifikasi fungsi `public.rls_auto_enable()` bertipe SECURITY DEFINER yang dapat dipanggil role umum. Migration produksi `otoclinic_revoke_public_rls_helper` sudah mencabut EXECUTE untuk `public`, `anon`, dan `authenticated`. Verifikasi advisor perlu diulang setelah perubahan.

## Prinsip non-negotiable
1. Schema Supabase live adalah sumber fakta; cocokkan dengan migration yang ada sebelum DDL selanjutnya.
2. Jangan masukkan data demo ke produksi dan jangan tampilkan angka contoh seolah-olah metrik nyata.
3. Fitment, kondisi, harga, dan stok hanya dinyatakan terverifikasi jika bukti tersedia.
4. Semua mutasi inventori harus melalui ledger dan mencatat alasan/aktor.
5. Aksi sensitif harus melalui backend terotorisasi, permission, dan audit.
6. Tidak ada kredensial service-role atau secret di frontend.
7. Jangan publikasikan gambar supplier/seller tanpa hak penggunaan yang jelas.

## Implementation plan
Lihat `docs/implementation/PHASES.md`, `docs/design-system/FOUNDATIONS.md`, dan `docs/architecture/BASELINE_AUDIT.md`.

## Deployment
Belum ada deployment target/build pipeline yang terkonfirmasi dari repository saat bootstrap. Jangan mengklaim production live sampai URL deployment, CI/build, environment variables, dan smoke tests diverifikasi. Semua implementasi kode baru dilakukan langsung ke `main` sesuai instruksi pemilik proyek, dengan perubahan schema produksi hanya melalui migration yang ditinjau dan additive.
