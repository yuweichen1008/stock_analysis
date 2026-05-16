import type { MetadataRoute } from "next";

const BASE_URL = "https://lokistock.com";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: BASE_URL,                   lastModified: new Date(), changeFrequency: "daily",   priority: 1.0 },
    { url: `${BASE_URL}/tws`,          lastModified: new Date(), changeFrequency: "hourly",  priority: 0.9 },
    { url: `${BASE_URL}/charts`,       lastModified: new Date(), changeFrequency: "hourly",  priority: 0.9 },
    { url: `${BASE_URL}/options`,      lastModified: new Date(), changeFrequency: "hourly",  priority: 0.8 },
    { url: `${BASE_URL}/weekly`,       lastModified: new Date(), changeFrequency: "weekly",  priority: 0.8 },
    { url: `${BASE_URL}/news`,         lastModified: new Date(), changeFrequency: "hourly",  priority: 0.8 },
    { url: `${BASE_URL}/trading`,      lastModified: new Date(), changeFrequency: "hourly",  priority: 0.7 },
    { url: `${BASE_URL}/backtest`,     lastModified: new Date(), changeFrequency: "weekly",  priority: 0.6 },
    { url: `${BASE_URL}/subscribe`,    lastModified: new Date(), changeFrequency: "monthly", priority: 0.5 },
  ];
}
