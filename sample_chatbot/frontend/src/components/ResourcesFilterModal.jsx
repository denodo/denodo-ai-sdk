import React, { useState, useEffect } from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";

const ResourcesFilterModal = ({
  show,
  handleClose,
  syncedResources,
  currentFilters,
  currentAllowExternalAssociations,
  onSave
}) => {
  const [selectedDatabases, setSelectedDatabases] = useState(
    currentFilters.databases || []
  );
  const [selectedTags, setSelectedTags] = useState(currentFilters.tags || []);
  const [allowExternalAssociations, setAllowExternalAssociations] = useState(
    currentAllowExternalAssociations
  );
  const dbNames = Object.keys(syncedResources?.DATABASE || {});
  const tagNames = Object.keys(syncedResources?.TAG || {});
  const hasData = dbNames.length > 0 || tagNames.length > 0;

  useEffect(() => {
    setSelectedDatabases(currentFilters.databases || []);
    setSelectedTags(currentFilters.tags || []);
    setAllowExternalAssociations(currentAllowExternalAssociations);
  }, [currentFilters, currentAllowExternalAssociations, show]);

  const handleDatabaseChange = (dbName) => {
    setSelectedDatabases((prev) =>
      prev.includes(dbName)
        ? prev.filter((db) => db !== dbName)
        : [...prev, dbName]
    );
  };

  const handleTagChange = (tagName) => {
    setSelectedTags((prev) =>
      prev.includes(tagName)
        ? prev.filter((tag) => tag !== tagName)
        : [...prev, tagName]
    );
  };

  const handleApply = () => {
    onSave({
      databases: selectedDatabases,
      tags: selectedTags,
      allowExternalAssociations: allowExternalAssociations,
    });
    handleClose();
  };

  const handleClear = () => {
    setSelectedDatabases([]);
    setSelectedTags([]);
    setAllowExternalAssociations(true);
    onSave({ databases: [], tags: [], allowExternalAssociations: true });
    handleClose();
  };

  const allDbsSelected =
    dbNames.length > 0 && selectedDatabases.length === dbNames.length;
  const someDbsSelected = selectedDatabases.length > 0 && !allDbsSelected;

  const handleSelectAllDbs = () => {
    if (allDbsSelected) {
      setSelectedDatabases([]);
    } else {
      setSelectedDatabases(dbNames);
    }
  };

  const allTagsSelected =
    tagNames.length > 0 && selectedTags.length === tagNames.length;
  const someTagsSelected = selectedTags.length > 0 && !allTagsSelected;

  const handleSelectAllTags = () => {
    if (allTagsSelected) {
      setSelectedTags([]);
    } else {
      setSelectedTags(tagNames);
    }
  };

  return (
    <Modal show={show} onHide={handleClose} centered>
      <Modal.Header closeButton>
        <Modal.Title>Context Selection</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p>
          These are the databases and tags the AI SDK has access to. You can
          limit here the context of what the AI SDK will have access to answer
          your question. If none are selected, all accessible resources will be
          used.
        </p>

        {!hasData && (
          <p className="text-muted">
            No synchronized resources found to filter by.
          </p>
        )}

        {dbNames.length > 0 && (
          <>
            <h5>Databases</h5>
            <div
              style={{ maxHeight: "150px", overflowY: "auto" }}
              className="border rounded p-2"
            >
              <Form>
                <Form.Check
                  type="checkbox"
                  label={allDbsSelected ? "Deselect All" : "Select All"}
                  id="db-select-all"
                  checked={allDbsSelected}
                  indeterminate={someDbsSelected}
                  onChange={handleSelectAllDbs}
                  className="fw-bold"
                />
                <hr className="my-1" />
                {dbNames.map((dbName) => (
                  <Form.Check
                    key={dbName}
                    type="checkbox"
                    label={dbName}
                    id={`db-check-${dbName}`}
                    checked={selectedDatabases.includes(dbName)}
                    onChange={() => handleDatabaseChange(dbName)}
                  />
                ))}
              </Form>
            </div>
          </>
        )}

        {tagNames.length > 0 && (
          <>
            <h5 className="mt-3">Tags</h5>
            <div
              style={{ maxHeight: "150px", overflowY: "auto" }}
              className="border rounded p-2"
            >
              <Form>
                <Form.Check
                  type="checkbox"
                  label={allTagsSelected ? "Deselect All" : "Select All"}
                  id="tag-select-all"
                  checked={allTagsSelected}
                  indeterminate={someTagsSelected}
                  onChange={handleSelectAllTags}
                  className="fw-bold"
                />
                <hr className="my-1" />
                {tagNames.map((tagName) => (
                  <Form.Check
                    key={tagName}
                    type="checkbox"
                    label={tagName}
                    id={`tag-check-${tagName}`}
                    checked={selectedTags.includes(tagName)}
                    onChange={() => handleTagChange(tagName)}
                  />
                ))}
              </Form>
            </div>
          </>
        )}

        {hasData && (
          <Form.Check
            type="switch"
            id="allow-external-assoc"
            label="Include associated views (even if outside the filtered context)"
            checked={allowExternalAssociations}
            onChange={(e) => setAllowExternalAssociations(e.target.checked)}
            className="mt-3"
          />
        )}
      </Modal.Body>
      <Modal.Footer>
        {hasData ? (
          <>
            <Button variant="light" onClick={handleClear}>
              Clear All
            </Button>
            <Button variant="dark" onClick={handleApply}>
              Apply
            </Button>
          </>
        ) : (
          <Button variant="light" onClick={handleClose}>
            Close
          </Button>
        )}
      </Modal.Footer>
    </Modal>
  );
};

export default ResourcesFilterModal;
