import { ShieldAlert } from "lucide-react";

/** Persistent, always-visible reminder of the access model — rendered as a
 * fixed strip under the Header on every authenticated screen. See DESIGN.md
 * §8: "every restricted screen carries a persistent … banner." */
export default function RestrictedBanner() {
  return (
    <div className="restricted-strip fixed top-[60px] left-[240px] right-0 h-[40px] z-10">
      <ShieldAlert size={14} className="flex-shrink-0" />
      <span>RESTRICTED — UPSI-ADJACENT — DO NOT FORWARD</span>
      <span className="hidden md:inline text-rose-500 font-normal">
        · This is a signal-flagging tool, not a valuation or due-diligence tool.
      </span>
    </div>
  );
}
