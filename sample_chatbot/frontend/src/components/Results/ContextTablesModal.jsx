import React, { useMemo } from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";

const ContextTablesModal = ({ show, onClose, tables, vql, dataCatalogUrl }) => {
  const { usedTables, unusedTables } = useMemo(() => {
    if (!tables || tables.length === 0) {
      return { usedTables: [], unusedTables: [] };
    }

    const cleanVql = vql?.replace(/"/g, "").toLowerCase() || "";
    const used = [];
    const unused = [];

    tables.forEach((table) => {
      const cleanTable = table.replace(/"/g, "").toLowerCase();
      const isUsedInVql = cleanVql.includes(cleanTable);
      if (isUsedInVql) {
        used.push(table);
      } else {
        unused.push(table);
      }
    });

    return { usedTables: used, unusedTables: unused };
  }, [tables, vql]);

  const renderTableButton = (table, index, variant) => {
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
            variant={variant}
            size="sm"
            className="me-2 mb-2 d-inline-flex align-items-center"
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
        variant={variant}
        size="sm"
        className="me-2 mb-2 d-inline-flex align-items-center"
      >
        {table.replace(/"/g, "")}
      </Button>
    );
  };

  return (
    <Modal show={show} onHide={onClose} size="lg" centered>
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>Context Tables</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {usedTables.length > 0 && (
          <div className="mb-4">
            <h6 className="mb-3">
              <strong>Used in Query ({usedTables.length})</strong>
            </h6>
            <div className="context-badges-container">
              {usedTables.map((table, index) =>
                renderTableButton(table, index, "success")
              )}
            </div>
          </div>
        )}

        {unusedTables.length > 0 && (
          <div className="mb-3">
            <h6 className="mb-3">
              <strong>
                Searched but Not Used ({unusedTables.length})
              </strong>
            </h6>
            <div className="context-badges-container">
              {unusedTables.map((table, index) =>
                renderTableButton(table, index, "secondary")
              )}
            </div>
          </div>
        )}

        <div className="mt-4 pt-3 border-top border-secondary">
          <small>
            <strong>Note:</strong> Views in green were used to find the answer,
            while grey tables were found in the database but found not relevant
            to the question.
          </small>
        </div>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="light" onClick={onClose}>
          Close
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default ContextTablesModal;


