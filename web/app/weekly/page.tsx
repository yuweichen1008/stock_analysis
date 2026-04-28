import WeeklyPage from "./WeeklyPage";

export const metadata = {
  title: "Weekly Signals — Oracle",
  description: "Contrarian weekly ±5% mean-reversion signals with put/call ratio overlay",
};

export default function Page() {
  return <WeeklyPage />;
}
