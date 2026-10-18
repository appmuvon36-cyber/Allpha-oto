import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "OtoClinic — Spare Part Otomotif",
    short_name: "OtoClinic",
    description: "Marketplace spare part mobil dan motor.",
    start_url: "/",
    display: "standalone",
    background_color: "#f5f6f8",
    theme_color: "#101b2b",
    lang: "id-ID",
    icons: [],
  };
}
