import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

interface PageMeta {
  title: string;
  subtitle?: string;
}

interface PageMetaContextValue {
  meta: PageMeta;
  setMeta: (meta: PageMeta) => void;
}

const PageMetaContext = createContext<PageMetaContextValue | null>(null);

export function PageMetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<PageMeta>({ title: "RPG Horizon Radar" });
  const value = useMemo(() => ({ meta, setMeta }), [meta]);
  return <PageMetaContext.Provider value={value}>{children}</PageMetaContext.Provider>;
}

export function usePageMetaContext() {
  const ctx = useContext(PageMetaContext);
  if (!ctx) throw new Error("usePageMetaContext must be used within a PageMetaProvider");
  return ctx;
}

/** Call once per page (e.g. `usePageMeta("Signal Board", "…")`) to drive the
 * fixed Header's title/subtitle without threading props through the Outlet
 * layout route. */
export function usePageMeta(title: string, subtitle?: string) {
  const { setMeta } = usePageMetaContext();
  useEffect(() => {
    setMeta({ title, subtitle });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, subtitle]);
}
