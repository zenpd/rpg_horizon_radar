import { useEffect, useRef } from "react";
import * as d3 from "d3";

import type { RippleEffect } from "../types";

const DEPENDENCY_COLOR: Record<string, string> = {
  raw_material: "#f59e0b",   // amber
  byproduct: "#14b8a6",      // teal
  shared_service: "#3b82f6", // blue
  shared_vendor: "#8b5cf6",  // violet
};

interface Node extends d3.SimulationNodeDatum {
  id: string;
  kind: "center" | "ripple";
  dependencyType?: string;
  relevance?: "direct" | "routine";
}

interface Link extends d3.SimulationLinkDatum<Node> {
  dependencyType: string;
}

interface RippleGraphProps {
  center: string;
  effects: RippleEffect[];
  height?: number;
}

export default function RippleGraph({ center, effects, height = 280 }: RippleGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || effects.length === 0) return;

    const width = container.clientWidth || 480;
    container.innerHTML = "";

    const nodes: Node[] = [
      { id: center, kind: "center" },
      ...effects.map((e) => ({ id: e.counterparty_name, kind: "ripple" as const, dependencyType: e.dependency_type, relevance: e.relevance })),
    ];
    const links: Link[] = effects.map((e) => ({ source: center, target: e.counterparty_name, dependencyType: e.dependency_type }));

    const svg = d3.select(container).append("svg")
      .attr("width", width).attr("height", height)
      .attr("viewBox", [0, 0, width, height]).attr("style", "max-width: 100%; height: auto;");

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink<Node, Link>(links).id((d) => d.id).distance(110))
      .force("charge", d3.forceManyBody().strength(-260))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(44));

    const link = svg.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", (d) => DEPENDENCY_COLOR[d.dependencyType] || "#cbd5e1")
      .attr("stroke-width", 1.5).attr("stroke-opacity", 0.55);

    const node = svg.append("g").selectAll<SVGGElement, Node>("g").data(nodes).join("g")
      .attr("cursor", "grab")
      .call(
        d3.drag<SVGGElement, Node>()
          .on("start", (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
          .on("end", (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    node.append("circle")
      .attr("r", (d) => (d.kind === "center" ? 30 : 22))
      .attr("fill", (d) => (d.kind === "center" ? "#4f46e5" : DEPENDENCY_COLOR[d.dependencyType || ""] || "#94a3b8"))
      .attr("fill-opacity", (d) => (d.kind === "ripple" && d.relevance === "routine" ? 0.55 : 1))
      .attr("stroke", "#fff").attr("stroke-width", 2);

    node.append("text")
      .attr("text-anchor", "middle").attr("dy", (d) => (d.kind === "center" ? 46 : 36))
      .attr("font-size", 11).attr("font-weight", 600).attr("fill", "#334155")
      .text((d) => (d.id.length > 18 ? d.id.slice(0, 16) + "…" : d.id));

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as Node).x!).attr("y1", (d) => (d.source as Node).y!)
        .attr("x2", (d) => (d.target as Node).x!).attr("y2", (d) => (d.target as Node).y!);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => { simulation.stop(); };
  }, [center, effects, height]);

  if (effects.length === 0) return null;
  return <div ref={containerRef} className="w-full" />;
}
