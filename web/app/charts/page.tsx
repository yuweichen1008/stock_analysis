import type { Metadata } from "next";
import ChartsPage from "./ChartsPage";

export const metadata: Metadata = { title: "Charts" };

export default function Page() {
  return <ChartsPage />;
}
