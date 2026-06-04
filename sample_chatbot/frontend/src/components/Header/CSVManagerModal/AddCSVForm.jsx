import React from 'react';
import PropTypes from 'prop-types';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Table from 'react-bootstrap/Table';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Popover from 'react-bootstrap/Popover';
import { getDelimiterLabel } from './utils';

const PREVIEW_VALUE_MAX = 200;

const truncateValue = (val) => {
  if (val === undefined || val === null) return '<value>';
  const str = String(val);
  return str.length > PREVIEW_VALUE_MAX ? `${str.slice(0, PREVIEW_VALUE_MAX)}…` : str;
};

const buildColumnHelpPopover = (preview, selected) => {
  // Pick up to three columns to illustrate, prefer ones the user has selected.
  const columns = preview?.columns || [];
  const sampleRow = preview?.rows?.[0] || {};
  const picks = (selected && selected.length ? selected : columns).slice(0, 3);

  return (
    <Popover id="vectorize-help-popover" style={{ maxWidth: '420px' }}>
      <Popover.Header as="h3">What does "columns to vectorize" mean?</Popover.Header>
      <Popover.Body style={{ fontSize: '0.85em' }}>
        <p className="mb-2">
          The <strong>selected columns</strong> become the searchable text that gets
          embedded. This means that the similarity search will be performed on the composite string of those columns.
          When searching, the knowledge_query tool will return this composite string.
        </p>
        <p className="mb-2">
          With your current pick the embedded text for the first row would be:
        </p>
        <div className="p-2 bg-light rounded mb-2" style={{ whiteSpace: 'pre-wrap' }}>
          {picks.length === 0 ? (
            <em>(pick at least one column)</em>
          ) : (
            picks.map((c, i) => (
              <div key={c} className={i < picks.length - 1 ? 'mb-2' : ''}>
                <strong>{c}:</strong> {truncateValue(sampleRow[c])}
              </div>
            ))
          )}
        </div>
        <hr />
        <p className="mb-0 text-muted">
          Tip: pick columns whose <em>meaning</em> answers questions (titles, descriptions,
          bodies). Skip IDs, timestamps and other columns that look like noise.
        </p>
      </Popover.Body>
    </Popover>
  );
};

const AddCSVForm = ({
  newCSV,
  setNewCSV,
  preview,
  isLoadingPreview,
  isGeneratingDescription,
  isAdding,
  currentUserIsAdmin,
  onSubmit,
  onCancel,
  onFileChange,
  onGenerateDescription
}) => {
  const columns = preview?.columns || [];
  const selected = newCSV.vectorizedColumns || [];

  const toggleColumn = (col) => {
    setNewCSV((prev) => {
      const current = new Set(prev.vectorizedColumns || []);
      if (current.has(col)) current.delete(col);
      else current.add(col);
      // Preserve column order from preview when storing.
      const ordered = columns.filter((c) => current.has(c));
      return { ...prev, vectorizedColumns: ordered };
    });
  };

  const setAll = (value) => {
    setNewCSV((prev) => ({ ...prev, vectorizedColumns: value ? [...columns] : [] }));
  };

  return (
    <div className="mb-4 p-3 border rounded">
      <h6>Add New CSV Source</h6>
      <Form onSubmit={onSubmit}>
        {newCSV.path ? (
          <Alert variant="light" className="py-2 mb-3">
            <small><strong>File:</strong> {newCSV.sourceName}.csv</small>
          </Alert>
        ) : (
          <Form.Group className="mb-3">
            <Form.Label>Select CSV file</Form.Label>
            <Form.Control type="file" accept=".csv" onChange={onFileChange} />
          </Form.Group>
        )}

        {isLoadingPreview && (
          <div className="mb-3 text-muted">
            <Spinner size="sm" className="me-2" />Loading preview...
          </div>
        )}

        {preview && (
          <div className="mb-3 p-2 bg-light rounded" style={{ fontSize: '0.85em' }}>
            <div className="mb-2">
              {newCSV.sourceName && (
                <span className="me-3"><strong>Collection name:</strong> {newCSV.sourceName}</span>
              )}
              <strong>Detected delimiter:</strong> {getDelimiterLabel(preview.delimiter)}
              <span className="ms-3"><strong>Columns:</strong> {preview.columns.length}</span>
            </div>
            <div style={{ maxHeight: '150px', overflowY: 'auto', overflowX: 'auto' }}>
              <Table size="sm" bordered style={{ fontSize: '0.8em', marginBottom: 0 }}>
                <thead>
                  <tr>
                    {preview.columns.map((col) => (
                      <th key={col} style={{ whiteSpace: 'nowrap', padding: '4px 8px' }}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, rowIdx) => {
                    const rowKey = `row-${Object.values(row).slice(0, 2).join('-')}-${rowIdx}`;
                    return (
                      <tr key={rowKey}>
                        {preview.columns.map((col) => (
                          <td key={col} style={{ whiteSpace: 'nowrap', padding: '4px 8px', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {row[col]}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            </div>
          </div>
        )}

        {columns.length > 0 && (
          <Form.Group className="mb-3">
            <Form.Label className="d-flex align-items-center">
              Columns to vectorize
              <OverlayTrigger
                trigger={['click', 'focus']}
                placement="right"
                rootClose
                overlay={buildColumnHelpPopover(preview, selected)}
              >
                <Button variant="link" size="sm" className="p-0 ms-2" title="What does this mean?">
                  <i className="bi bi-question-circle text-secondary"></i>
                </Button>
              </OverlayTrigger>
              <span className="ms-auto">
                <Button variant="link" size="sm" className="p-0 me-2" onClick={() => setAll(true)}>Select all</Button>
                <Button variant="link" size="sm" className="p-0" onClick={() => setAll(false)}>None</Button>
              </span>
            </Form.Label>
            <div className="d-flex flex-wrap gap-2 p-2 border rounded bg-white">
              {columns.map((col) => {
                const isChecked = selected.includes(col);
                return (
                  <Form.Check
                    key={col}
                    type="checkbox"
                    id={`vectorize-col-${col}`}
                    label={col}
                    checked={isChecked}
                    onChange={() => toggleColumn(col)}
                    className="me-2"
                  />
                );
              })}
            </div>
            <Form.Text muted>
              Selected: {selected.length}/{columns.length}. At least one column is required.
            </Form.Text>
          </Form.Group>
        )}

        <Form.Group className="mb-3">
          <Form.Label>Delimiter</Form.Label>
          <Form.Control
            type="text"
            maxLength={1}
            value={newCSV.delimiter}
            onChange={(e) => setNewCSV((prev) => ({ ...prev, delimiter: e.target.value }))}
            style={{ width: '60px' }}
          />
        </Form.Group>

        <Form.Group className="mb-3">
          <Form.Label>
            Description *
            {(newCSV.file || newCSV.path) && (
              <Button
                variant="outline-primary"
                size="sm"
                className="ms-2"
                onClick={onGenerateDescription}
                disabled={isGeneratingDescription}
              >
                {isGeneratingDescription ? (
                  <><Spinner size="sm" className="me-1" />Generating...</>
                ) : '✨ Suggest Description with AI'}
              </Button>
            )}
          </Form.Label>
          <Form.Control
            as="textarea"
            rows={3}
            placeholder="Describe the contents of the CSV file"
            value={newCSV.description}
            onChange={(e) => setNewCSV((prev) => ({ ...prev, description: e.target.value }))}
            required
          />
        </Form.Group>

        {currentUserIsAdmin ? (
          <Form.Group className="mb-3">
            <Form.Check
              type="switch"
              id="csv-private-toggle"
              label={
                <span>
                  <i className={`bi ${newCSV.private ? 'bi-lock-fill' : 'bi-unlock'} me-1`} />
                  Private — only you can see this collection
                </span>
              }
              checked={!!newCSV.private}
              onChange={(e) => setNewCSV((prev) => ({ ...prev, private: e.target.checked }))}
            />
            <Form.Text muted>
              As an admin you can publish this collection. Toggle off to make it public for
              everyone using this chatbot. Only the owner can later delete it or edit its description.
            </Form.Text>
          </Form.Group>
        ) : (
          <Alert variant="light" className="py-2 mb-3 d-flex align-items-center">
            <i className="bi bi-lock-fill me-2 text-dark" />
            <small className="mb-0">
              This collection will be <strong>private</strong> — only visible to you.
              Only an admin can publish a collection.
            </small>
          </Alert>
        )}

        <div className="d-flex gap-2">
          <Button variant="light" onClick={onCancel}>Cancel</Button>
          <Button
            variant="dark"
            type="submit"
            disabled={
              isAdding
              || !newCSV.description
              || (!newCSV.file && !newCSV.path)
              || selected.length === 0
            }
          >
            {isAdding ? <Spinner size="sm" /> : 'Add Source'}
          </Button>
        </div>
      </Form>
    </div>
  );
};

AddCSVForm.propTypes = {
  newCSV: PropTypes.shape({
    file: PropTypes.object,
    description: PropTypes.string,
    delimiter: PropTypes.string,
    path: PropTypes.string,
    sourceName: PropTypes.string,
    vectorizedColumns: PropTypes.arrayOf(PropTypes.string),
    private: PropTypes.bool
  }).isRequired,
  setNewCSV: PropTypes.func.isRequired,
  preview: PropTypes.shape({
    delimiter: PropTypes.string,
    columns: PropTypes.arrayOf(PropTypes.string),
    rows: PropTypes.arrayOf(PropTypes.object)
  }),
  isLoadingPreview: PropTypes.bool.isRequired,
  isGeneratingDescription: PropTypes.bool.isRequired,
  isAdding: PropTypes.bool.isRequired,
  currentUserIsAdmin: PropTypes.bool,
  onSubmit: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
  onFileChange: PropTypes.func.isRequired,
  onGenerateDescription: PropTypes.func.isRequired
};

export default AddCSVForm;
