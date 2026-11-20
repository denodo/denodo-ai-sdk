import React from "react";
import { GraphFence } from "./inlineGraphs";

const MarkdownImage = ({ node, src, alt, ...props }) => {
  const marker = "inline-graph/";
  if (typeof src === "string" && src.includes(marker)) {
    const graphId = decodeURIComponent(src.slice(src.indexOf(marker) + marker.length));
    return <GraphFence graphId={graphId} />;
  }
  return <img src={src} alt={alt} {...props} />;
};

export const markdownComponents = {
  a: ({ node, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
  table: ({ node, ...props }) => (
    <div
      className="markdown-table-scroll"
      tabIndex={0}
      role="region"
      aria-label="Scrollable result table"
    >
      <table {...props} />
    </div>
  ),
  img: MarkdownImage,
};
