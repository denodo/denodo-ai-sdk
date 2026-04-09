import React, { useState, useEffect, useMemo } from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";

const ResourcesFilterModal = ({
  show,
  handleClose,
  syncedResources,
  partialResources,
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

  const { allDbNames, allTagNames, isDbPartial, isTagPartial } = useMemo(() => {
    const syncedDbs = Object.keys(syncedResources?.DATABASE || {});
    const syncedTags = Object.keys(syncedResources?.TAG || {});

    const partialDbSet = new Set();
    const partialTagSet = new Set();

    const pDbsByTag = partialResources?.partial_dbs_by_tag || {};
    Object.values(pDbsByTag).forEach((dbList) => {
      dbList.forEach((db) => partialDbSet.add(db));
    });

    const pTagsByDb = partialResources?.partial_tags_by_db || {};
    Object.values(pTagsByDb).forEach((tagList) => {
      tagList.forEach((tag) => partialTagSet.add(tag));
    });

    const pTagsByTag = partialResources?.partial_tags_by_tag || {};
    Object.values(pTagsByTag).forEach((tagList) => {
      tagList.forEach((tag) => partialTagSet.add(tag));
    });

    const combinedDbs = Array.from(new Set([...syncedDbs, ...partialDbSet])).sort();
    const combinedTags = Array.from(new Set([...syncedTags, ...partialTagSet])).sort();

    return {
      allDbNames: combinedDbs,
      allTagNames: combinedTags,
      isDbPartial: (name) => !syncedDbs.includes(name) && partialDbSet.has(name),
      isTagPartial: (name) => !syncedTags.includes(name) && partialTagSet.has(name)
    };
  }, [syncedResources, partialResources]);

  const hasData = allDbNames.length > 0 || allTagNames.length > 0;
  const hasPartials = allDbNames.some(isDbPartial) || allTagNames.some(isTagPartial);

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
    allDbNames.length > 0 && selectedDatabases.length === allDbNames.length;
  const someDbsSelected = selectedDatabases.length > 0 && !allDbsSelected;

  const handleSelectAllDbs = () => {
    if (allDbsSelected) {
      setSelectedDatabases([]);
    } else {
      setSelectedDatabases(allDbNames);
    }
  };

  const allTagsSelected =
    allTagNames.length > 0 && selectedTags.length === allTagNames.length;
  const someTagsSelected = selectedTags.length > 0 && !allTagsSelected;

  const handleSelectAllTags = () => {
    if (allTagsSelected) {
      setSelectedTags([]);
    } else {
      setSelectedTags(allTagNames);
    }
  };

  const renderLabel = (name, isPartial) => (
    <span>
      {name}
      {isPartial && (
        <span className="text-muted ms-1" style={{ fontSize: "0.85em", fontStyle: "italic" }}>
          (partial)
        </span>
      )}
    </span>
  );

  return (
    <Modal show={show} onHide={handleClose} centered>
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>Context Selection</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p>
          These are the databases and tags the AI SDK has access to. You can
          limit here the context of what the AI SDK will have access to answer
          your question. If none are selected, all accessible resources will be
          used.
        </p>

        {hasPartials && (
          <div className="alert alert-light border p-2 mb-3" style={{ fontSize: "0.9em" }}>
            <strong>Note:</strong> Resources marked as (partial) have not been directly 
            synchronized but were found associated with other synchronized resources.
          </div>
        )}

        {!hasData && (
          <p className="text-muted">
            No synchronized resources found to filter by.
          </p>
        )}

        {allDbNames.length > 0 && (
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
                  ref={(input) => {
                    if (input) input.indeterminate = someDbsSelected;
                  }}
                  onChange={handleSelectAllDbs}
                  className="fw-bold"
                />
                <hr className="my-1" />
                {allDbNames.map((dbName) => (
                  <Form.Check
                    key={dbName}
                    type="checkbox"
                    label={renderLabel(dbName, isDbPartial(dbName))}
                    id={`db-check-${dbName}`}
                    checked={selectedDatabases.includes(dbName)}
                    onChange={() => handleDatabaseChange(dbName)}
                  />
                ))}
              </Form>
            </div>
          </>
        )}

        {allTagNames.length > 0 && (
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
                  ref={(input) => {
                    if (input) input.indeterminate = someTagsSelected;
                  }}
                  onChange={handleSelectAllTags}
                  className="fw-bold"
                />
                <hr className="my-1" />
                {allTagNames.map((tagName) => (
                  <Form.Check
                    key={tagName}
                    type="checkbox"
                    label={renderLabel(tagName, isTagPartial(tagName))}
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
