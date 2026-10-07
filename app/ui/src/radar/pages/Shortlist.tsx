import { SignalBoard } from "./Signals";

/** Radar → Shortlisted signals: the M&A signals shortlisted from their acquisition thesis. */
export default function Shortlist() {
  return <SignalBoard title="Shortlisted signals" tabs={[["shortlisted", "Shortlisted"]]}
    intro="Signals shortlisted from their acquisition thesis. View opens the thesis again; Remove from shortlist sends a signal back to M&A Signals."
    empty={{ shortlisted: "Nothing shortlisted yet. Open a signal in M&A Signals and press Shortlist in its thesis." }} />;
}
