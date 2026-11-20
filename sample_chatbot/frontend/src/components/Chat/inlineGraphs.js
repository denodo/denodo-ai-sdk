import React, { createContext, useContext, useMemo } from "react";

const InlineGraphsContext = createContext({
  graphsById: {},
  onOpenGraph: null,
});

const graphFence = () => /```graph[ \t]*\r?\n+([^\s`]+)[ \t]*\r?\n+```/g;

export const replaceGraphFences = (content) => {
  if (!content) return content;
  return String(content).replace(
    graphFence(),
    (_, graphId) => `\n\n![graph](inline-graph/${graphId})\n\n`,
  );
};

export const isInlineGraphSource = (raw) => {
  return typeof raw === "string" && raw.startsWith("data:image") && raw.length > 300;
};

const graphsByToolCallId = (blocks) => {
  const graphs = {};
  if (!Array.isArray(blocks)) return graphs;
  for (const block of blocks) {
    if (!block || block.type !== "tool" || !block.toolCallId) continue;
    const raw = block.artifact && block.artifact.raw_graph;
    if (isInlineGraphSource(raw)) {
      graphs[block.toolCallId] = {
        src: raw,
        vql: (block.artifact && block.artifact.vql) || (block.args && block.args.vql) || "",
      };
    }
  }
  return graphs;
};

export const InlineGraphsProvider = ({ blocks, onOpenGraph, children }) => {
  const graphsById = useMemo(() => graphsByToolCallId(blocks), [blocks]);
  const value = useMemo(
    () => ({ graphsById, onOpenGraph }),
    [graphsById, onOpenGraph],
  );
  return (
    <InlineGraphsContext.Provider value={value}>
      {children}
    </InlineGraphsContext.Provider>
  );
};

const useInlineGraphs = () => useContext(InlineGraphsContext);

export const GraphFence = ({ graphId }) => {
  const { graphsById, onOpenGraph } = useInlineGraphs();
  const entry = graphsById[graphId];
  if (!entry) {
    return <span className="inline-graph-missing">Graph unavailable.</span>;
  }
  return (
    <img
      className="inline-graph"
      src={entry.src}
      alt="Graph"
      onClick={() => onOpenGraph(entry)}
    />
  );
};
