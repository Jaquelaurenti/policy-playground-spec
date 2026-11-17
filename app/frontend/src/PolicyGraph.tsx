// DAG da política (task 14): parâmetros → regras por camada de execution_order → saídas.
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react";
import { useMemo } from "react";
import type { Json } from "./api";
import { outputLabel, paramLabel, withUnit } from "./labels";

export const AREA_COLOR: Record<string, string> = { Extraction: "#2f5bd3", "Hard filters": "#b42318", ETL: "#9a5b00", "Final base": "#1b7a4b" };

export default function PolicyGraph({ policy, highlight, focus, onSelect }: {
  policy: Json; highlight: Set<string>; focus: Set<string>; onSelect: (id: string) => void;
}) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    const X = 200, Y = 86;
    policy.parameters.forEach((p: Json, i: number) => nodes.push({
      id: p.id, position: { x: 0, y: 150 + i * Y }, data: { label: `${paramLabel(p)}\n${withUnit(p.value, p.unit)}` },
      style: nodeStyle("#7a4dd8", highlight.has(p.id), focus.has(p.id)),
    }));
    policy.executionOrder.forEach((layer: string[], li: number) => layer.forEach((rid, ri) => {
      const r = policy.rules.find((x: Json) => x.id === rid);
      nodes.push({ id: rid, position: { x: X * (li + 1), y: 30 + ri * Y + (li % 2) * 20 },
        data: { label: r.name }, style: nodeStyle(AREA_COLOR[r.area] || "#5a606b", highlight.has(rid), focus.has(rid)) });
      r.dependsOn.forEach((d: string) => edges.push(edge(d, rid, highlight.has(d) && highlight.has(rid))));
      r.parameters.forEach((p: string) => edges.push(edge(p, rid, highlight.has(p) && highlight.has(rid))));
    }));
    const last = policy.executionOrder.length + 1;
    policy.outputVars.forEach((o: string, i: number) => {
      const producer = policy.variables.find((v: Json) => v.name === o)?.produced_by;
      nodes.push({ id: `out:${o}`, position: { x: X * last, y: 60 + i * Y }, data: { label: outputLabel(o) },
        style: nodeStyle("#14161b", highlight.has(o), false) });
      if (producer) edges.push(edge(producer, `out:${o}`, highlight.has(producer) && highlight.has(o)));
    });
    return { nodes, edges };
  }, [policy, highlight, focus]);

  return (
    <div className="graph">
      <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.3} nodesDraggable={false} nodesConnectable={false}
        onNodeClick={(_, n) => !n.id.startsWith("out:") && onSelect(n.id)} proOptions={{ hideAttribution: true }}>
        <Background gap={18} color="#e3e6eb" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function nodeStyle(color: string, hot: boolean, focus: boolean) {
  return { border: `2px solid ${color}`, borderRadius: 10, padding: 8, width: 170, fontSize: 12.5, whiteSpace: "pre-line" as const, cursor: "pointer",
    background: hot ? "#fbe7f0" : "#fff", boxShadow: focus ? "0 0 0 4px rgba(154,91,0,.35)" : hot ? "0 0 0 3px rgba(179,21,90,.25)" : "none",
    fontWeight: hot ? 700 : 500, color: "#14161b" };
}

function edge(source: string, target: string, hot: boolean): Edge {
  return { id: `${source}->${target}`, source, target, animated: hot, markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: hot ? "#b3155a" : "#aeb6c4", strokeWidth: hot ? 2.4 : 1.2 } };
}
