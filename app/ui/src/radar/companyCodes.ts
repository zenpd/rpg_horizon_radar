// Radar company display name <-> governed-backend subsidiary code (matches
// app/radar/bridge.py's CODE_TO_CO). Shared by the Executive Dashboard and
// the Deep-dive Analysis Workspace, which both need to cross between the
// two systems' naming.
export const CO_TO_CODE: Record<string, string> = {
  CEAT: "CEAT", KEC: "KEC", Zensar: "ZENSAR", "RPG Life Sciences": "RPGLS",
  "Raychem RPG": "RAYCHEM", Harrisons: "HARRISONS",
};

export const CODE_TO_CO: Record<string, string> = Object.fromEntries(
  Object.entries(CO_TO_CODE).map(([co, code]) => [code, co])
);
