import React from "react";
import Button from "react-bootstrap/Button";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";

const renderTooltip = (content) => (
  <Tooltip id="context-tooltip">{content}</Tooltip>
);

const ContextTablesStrip = ({ tables, vql, dataCatalogUrl, icons, onOpenContext }) => {
  if (!tables || tables.length === 0) {
    return icons || null;
  }

  const cleanVql = vql?.replace(/"/g, "").toLowerCase() || "";

  const usedTables = [];
  const unusedTables = [];

  tables.forEach((table) => {
    const cleanTable = table.replace(/"/g, "").toLowerCase();
    const isUsedInVql = cleanVql.includes(cleanTable);

    if (isUsedInVql) {
      usedTables.push(table);
    } else {
      unusedTables.push(table);
    }
  });

  const renderTableButton = (table, index, isUsed = true) => {
    const cleanTable = table.replace(/"/g, "").toLowerCase();
    const tableParts = cleanTable.split(".");
    const schema = tableParts[0];
    const tableName = tableParts[1] || schema;

    const catalogUrl = dataCatalogUrl
      ? `${dataCatalogUrl}/#/view/${schema}/${tableName}`
      : null;

    if (catalogUrl) {
      return (
        <a
          key={index}
          href={catalogUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-decoration-none"
        >
          <Button
            variant={isUsed ? "success" : "secondary"}
            size="sm"
            bsPrefix="btn"
            className="me-1 mb-1 d-inline-flex align-items-center"
          >
            <img
              src="view.svg"
              alt="View"
              width="16"
              height="16"
              className="me-1"
            />
            {table.replace(/"/g, "")}
          </Button>
        </a>
      );
    }

    return (
      <Button
        key={index}
        variant={isUsed ? "success" : "secondary"}
        size="sm"
        bsPrefix="btn"
        className="me-1 mb-1 d-inline-flex align-items-center"
        style={isUsed ? { backgroundColor: "#143142", borderColor: "#143142" } : {}}
      >
        {table.replace(/"/g, "")}
      </Button>
    );
  };

  const hasTableButtons = usedTables.length > 0 || unusedTables.length > 0;

  return (
    <div
      style={{
        backgroundColor: "transparent",
        padding: "1rem 0",
        marginBottom: "0",
      }}
    >
      <div
        className={`mb-2 d-flex ${
          hasTableButtons ? "justify-content-between" : "justify-content-end"
        } align-items-center`}
      >
        {hasTableButtons && (
          <div className="context-badges-container">
            {usedTables.map((table, index) =>
              renderTableButton(table, index, true)
            )}
            {unusedTables.length > 0 && (
              <OverlayTrigger
                placement="top"
                delay={{ show: 250, hide: 400 }}
                overlay={renderTooltip("View all searched tables")}
              >
                <Button
                  variant="outline-info"
                  size="sm"
                  className="me-1 mb-1 d-inline-flex align-items-center context-more-btn"
                  onClick={() => onOpenContext(tables, vql)}
                >
                  +{unusedTables.length} more
                </Button>
              </OverlayTrigger>
            )}
          </div>
        )}
        {icons && (
          <div
            className="d-flex flex-row align-items-center"
            style={{ gap: "8px" }}
          >
            {icons}
          </div>
        )}
      </div>
    </div>
  );
};

export default ContextTablesStrip;


