import React, { useId, useMemo } from "react";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import { ViewChip } from "../QuestionForm/ContextViewsRow";
import {
  splitUsedTables,
  buildViewTokenLookup,
  viewTokens,
  cleanViewName,
} from "../../utils/viewUsage";

const renderTooltip = (id, content) => (
  <Tooltip id={id}>{content}</Tooltip>
);

// Views searched for an answer, shown at the bottom of the answer card.
// Views actually referenced by the generated VQL appear as green chips in
// the current context-view chip format; the rest sit behind a "+N more"
// chip that opens the Context Tables modal. If no view was used, no chips
// are shown at all.
const ContextTablesAction = ({ tables, vql, dataCatalogUrl, icons, onOpenContext, contextViews }) => {
  const tooltipId = `context-tooltip-${useId().replace(/[^A-Za-z0-9_-]/g, "")}`;
  const { usedTables, unusedTables } = useMemo(
    () => splitUsedTables(tables, vql, contextViews),
    [tables, vql, contextViews],
  );
  const tokenLookup = useMemo(
    () => buildViewTokenLookup(contextViews),
    [contextViews],
  );

  if (usedTables.length === 0) {
    if (!icons) return null;
    return (
      <div
        style={{
          backgroundColor: "transparent",
          padding: "1rem 0",
          marginBottom: "0",
        }}
      >
        <div className="mb-2 d-flex justify-content-end align-items-center">
          <div
            className="d-flex flex-row align-items-center"
            style={{ gap: "8px" }}
          >
            {icons}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        backgroundColor: "transparent",
        padding: "1rem 0",
        marginBottom: "0",
      }}
    >
      <div className="mb-2 d-flex justify-content-between align-items-center">
        <div className="context-badges-container d-flex flex-wrap align-items-center" style={{ gap: "8px", flex: 1, minWidth: 0 }}>
          {usedTables.map((table) => (
            <ViewChip
              key={table}
              view={{ name: cleanViewName(table), tokens: viewTokens(table, tokenLookup) }}
              dataCatalogUrl={dataCatalogUrl}
              showHint={false}
              used
            />
          ))}
          {unusedTables.length > 0 && (
            <OverlayTrigger
              placement="top"
              delay={{ show: 250, hide: 400 }}
              overlay={renderTooltip(tooltipId, "View all searched tables")}
            >
              <button
                type="button"
                className="context-view-more-chip"
                onClick={() => onOpenContext(tables, vql)}
              >
                +{unusedTables.length} more
              </button>
            </OverlayTrigger>
          )}
        </div>
        {icons && (
          <div
            className="d-flex flex-row align-items-center"
            style={{ gap: "8px", flexShrink: 0 }}
          >
            {icons}
          </div>
        )}
      </div>
    </div>
  );
};

export default ContextTablesAction;
