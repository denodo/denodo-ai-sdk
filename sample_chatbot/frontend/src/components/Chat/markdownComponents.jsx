import React from "react";

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
};
