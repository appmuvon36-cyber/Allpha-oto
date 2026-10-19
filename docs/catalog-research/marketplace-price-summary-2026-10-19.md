# Riset Katalog Marketplace OtoClinic — 19 Oktober 2026

## Cakupan dan hasil terverifikasi

- **108 listing unik Tokopedia** yang terambil dari halaman toko dan halaman pencarian kategori; tidak diklaim sebagai seluruh inventaris marketplace.
- **78 listing memiliki URL gambar langsung** dari metadata/kartu produk. URL gambar marketplace bisa bertanda tangan dan kedaluwarsa; alur impor Admin telah diperluas untuk mencoba memperbarui URL dari metadata listing sebelum mengunduh.
- **101 listing memiliki sinyal jumlah terjual yang terlihat**; 93 memiliki rating produk. Sinyal toko (misalnya total penjualan toko) dipisahkan dari jumlah terjual per produk.
- **Kondisi terverifikasi dari judul:** 2 listing; **kondisi belum terverifikasi:** 106. Kondisi yang tidak terbukti tidak ditebak. Kandidat unknown dapat masuk draft tetapi database menolak transisi ke review/approved/published sampai kondisi diverifikasi.
- Rentang harga listing yang teramati: **Rp5.975–Rp2.800.000**. Rentang keseluruhan ini bukan perbandingan produk sejenis; lihat harga per listing pada CSV.
- **Shopee:** 16 benchmark tambahan dicatat dalam `shopee-search-benchmarks-2026-10-19.csv` berdasarkan cuplikan hasil pencarian/kategori yang terlihat. Halaman produk Shopee yang dicoba meminta login/menampilkan verifikasi trafik, sehingga benchmark ini bukan PDP yang terverifikasi dan ditandai `import_eligible=no`; tidak digunakan sebagai produk draft atau bukti foto. Nilai ini hanya petunjuk awal untuk riset harga lintas platform, bukan pembanding final.

## Toko dan sinyal popularitas yang terlihat

- **Sparepart Ku (Tokopedia):** 70 listing sparepart motor dalam sampel, rating toko 4,7; 57 listing memiliki rating produk, rata-rata sekitar 4,63; 64 listing menampilkan sinyal terjual. Angka ini berasal dari cuplikan toko dan tidak berarti seluruh 70 produk adalah bestseller.
- **Lestari Motor 2 Jakarta Barat:** 10 listing terambil, 10 memiliki rating produk, rata-rata sekitar 4,99; rating toko tidak terlihat pada hasil yang diambil.
- **HSR WHEEL BANZAI RIMS:** 5 listing ban/velg, seluruhnya memiliki rating produk sekitar 5,0; rating toko dan volume pencarian tidak terlihat.
- **PUSAT AKI SURABAYA:** 5 listing aki, rata-rata rating produk sekitar 4,94; rating toko tidak terlihat.
- **Ban Motor Michelin Bekasi:** 4 listing ban, rata-rata rating produk sekitar 4,90; rating toko tidak terlihat.

Ini adalah shortlist untuk verifikasi pemasok, bukan klaim bahwa toko-toko tersebut pasti paling baik. Verifikasi kebijakan retur, faktur, garansi, stok nyata, dan kesesuaian part sebelum pembelian.

## Rentang harga observasi per kategori

Rentang berikut adalah harga listing yang terlihat, **bukan rentang harga final per kondisi**; variasi merek, paket, ukuran, dan kondisi dapat membuat rentang kategori terlalu lebar.

| Kategori | Listing | Harga terendah | Median observasi | Harga tertinggi |
|---|---:|---:|---:|---:|
| CVT / transmisi motor | 17 | Rp16.833 | Rp120.560 | Rp509.780 |
| Suspensi motor | 13 | Rp8.329 | Rp119.025 | Rp419.204 |
| Aki / sistem pengisian | 12 | Rp73.528 | Rp180.000 | Rp348.000 |
| Ban mobil | 11 | Rp664.587 | Rp711.000 | Rp1.382.472 |
| Kelistrikan motor | 10 | Rp9.567 | Rp19.141 | Rp368.720 |
| Sistem rem motor | 7 | Rp13.704 | Rp19.911 | Rp54.293 |
| Busi / pengapian | 7 | Rp7.494 | Rp10.902 | Rp149.999 |
| Velg mobil | 3 | Rp900.000 | Rp1.575.000 | Rp2.800.000 |

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

- `marketplace-observations-2026-10-19.csv`: seluruh data listing Tokopedia dan sumber.
- `shopee-search-benchmarks-2026-10-19.csv`: 16 cuplikan harga Shopee yang belum layak diimpor.
- `otoclinic-draft-import-batch-01.csv`: 100 kandidat untuk impor Admin.
- `otoclinic-draft-import-batch-02.csv`: 8 kandidat sisanya.

## Implementasi alur Admin/FastAPI

- CSV impor mengosongkan kolom SKU agar FastAPI mengalokasikan SKU resmi per kategori saat impor.
- Foto referensi marketplace disalin melalui `POST /v1/admin/catalog/products/{product_id}/media/import-marketplace` ke bucket privat `product-media`; URL CDN bertanda tangan akan diperbarui dari metadata listing bila memungkinkan.
- Status hak foto selalu `unknown` dan review media `pending`; publikasi foto memerlukan bukti hak penggunaan yang sah.
- Kondisi `unknown` hanya dapat disimpan sebagai draft. Constraint database menolak transisi ke review/approved/published sampai kondisi diverifikasi.
