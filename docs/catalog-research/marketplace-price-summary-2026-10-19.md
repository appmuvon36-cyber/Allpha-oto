# Riset Katalog Marketplace OtoClinic — 19 Oktober 2026

## Cakupan dan hasil terverifikasi

- **108 listing unik Tokopedia** yang terambil dari halaman toko dan halaman pencarian kategori; tidak diklaim sebagai seluruh inventaris marketplace.
- **78 listing memiliki URL gambar langsung** dari metadata/kartu produk. URL gambar marketplace bisa bertanda tangan dan kedaluwarsa; alur impor Admin telah diperluas untuk mencoba memperbarui URL dari metadata listing sebelum mengunduh.
- **101 listing memiliki sinyal jumlah terjual yang terlihat**; 93 memiliki rating produk. Sinyal toko (misalnya total penjualan toko) dipisahkan dari jumlah terjual per produk.
- **Kondisi terverifikasi dari judul:** 2 listing; **kondisi belum terverifikasi:** 106. Kondisi yang tidak terbukti tidak ditebak. Kandidat unknown dapat masuk draft tetapi database menolak transisi ke review/approved/published sampai kondisi diverifikasi.
- Rentang harga listing yang teramati: **Rp5.975–Rp2.800.000**. Rentang keseluruhan ini bukan perbandingan produk sejenis; lihat harga per listing pada CSV.
- **Shopee:** pencarian publik menghasilkan cuplikan harga dan sinyal populer, tetapi halaman produk yang dicoba meminta login/menampilkan verifikasi trafik. Nilai Shopee tidak direkayasa dan tidak digabung ke 108 listing terstruktur. File benchmark Shopee terpisah akan diperlukan untuk perbandingan harga lintas platform.

## Metode harga

Harga draft awal memakai harga listing aktif tertinggi dari kelompok dengan nama dan kategori identik jika ada; bila tidak ada pembanding identik, memakai harga yang terlihat pada listing. Ini **harga sementara**, bukan rekomendasi final lintas kondisi. Untuk memenuhi arahan memilih harga mendekati sisi termahal secara valid, bandingkan hanya produk dengan nomor part/ukuran, kondisi, paket, dan kompatibilitas yang sama. Harga bekas tidak dibandingkan dengan harga baru, dan harga promo coret bukan harga transaksi aktif.

## Foto dan hak penggunaan

URL gambar disimpan sebagai referensi marketplace dan diimpor ke bucket Supabase `product-media` privat melalui endpoint FastAPI baru. Metadata media selalu `rights_status=unknown`, `review_status=pending`, bukan foto publik. Foto tidak boleh disetujui atau dipublikasikan sebelum izin tertulis/lisensi penggunaan diverifikasi.

## Batas data yang wajib ditinjau sebelum publikasi

- SKU dialokasikan saat impor melalui API `/v1/admin/catalog/sku/next` dari kategori master aktif, bukan dibuat dari angka rekaan di file.
- Berat paket pada CSV adalah **estimasi sementara** untuk draft, bukan berat aktual. Timbang/konfirmasi sebelum publikasi karena berdampak pada ongkir.
- Kompatibilitas yang disebut pada judul marketplace adalah petunjuk awal. Tabel master varian kendaraan produksi masih kosong; jangan membuat fitment terverifikasi tanpa bukti nomor part/pabrikan.
- Stok marketplace bukan stok OtoClinic. Stok OtoClinic tidak dicatat dari angka listing; lakukan penerimaan inventaris setelah pemasok dan kuantitas fisik dikonfirmasi.
- Foto, kondisi, fitment, berat, stok, garansi, dan harga final tetap harus direview sebelum produk keluar dari draft.

## File

- `marketplace-observations-2026-10-19.csv`: seluruh data listing dan sumber.
- `otoclinic-draft-import-batch-01.csv`: 100 kandidat untuk impor Admin.
- `otoclinic-draft-import-batch-02.csv`: 8 kandidat sisanya.
