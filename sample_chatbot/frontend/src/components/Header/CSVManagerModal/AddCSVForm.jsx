import React from 'react';
import PropTypes from 'prop-types';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Badge from 'react-bootstrap/Badge';
import Table from 'react-bootstrap/Table';
import { getDelimiterLabel } from './utils';

const AddCSVForm = ({
  newCSV,
  setNewCSV,
  preview,
  isLoadingPreview,
  isGeneratingDescription,
  isAdding,
  onSubmit,
  onCancel,
  onFileChange,
  onGenerateDescription
}) => {
  return (
    <div className="mb-4 p-3 border rounded">
      <h6>
        Add New CSV Source{' '}
        {newCSV.sourceName && (
          <Badge bg="secondary" className="ms-2">
            {newCSV.sourceName}
          </Badge>
        )}
      </h6>
      <Form onSubmit={onSubmit}>
        {/* Only show file picker if not adding from scanned file */}
        {newCSV.path ? (
          <Alert variant="light" className="py-2 mb-3">
            <small>
              <strong>File:</strong> {newCSV.sourceName}.csv
            </small>
          </Alert>
        ) : (
          <Form.Group className="mb-3">
            <Form.Label>Select CSV file</Form.Label>
            <Form.Control type="file" accept=".csv" onChange={onFileChange} />
          </Form.Group>
        )}

        {isLoadingPreview && (
          <div className="mb-3 text-muted">
            <Spinner size="sm" className="me-2" />
            Loading preview...
          </div>
        )}

        {preview && (
          <div className="mb-3 p-2 bg-light rounded" style={{ fontSize: '0.85em' }}>
            <div className="mb-2">
              <strong>Detected delimiter:</strong> {getDelimiterLabel(preview.delimiter)}
              <span className="ms-3">
                <strong>Columns:</strong> {preview.columns.length}
              </span>
            </div>
            <div style={{ maxHeight: '150px', overflowY: 'auto', overflowX: 'auto' }}>
              <Table size="sm" bordered style={{ fontSize: '0.8em', marginBottom: 0 }}>
                <thead>
                  <tr>
                    {preview.columns.map((col) => (
                      <th key={col} style={{ whiteSpace: 'nowrap', padding: '4px 8px' }}>
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, rowIdx) => {
                    const rowKey = `row-${Object.values(row).slice(0, 2).join('-')}-${rowIdx}`;
                    return (
                    <tr key={rowKey}>
                      {preview.columns.map((col) => (
                        <td
                          key={col}
                          style={{
                            whiteSpace: 'nowrap',
                            padding: '4px 8px',
                            maxWidth: '200px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis'
                          }}
                        >
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
                  <>
                    <Spinner size="sm" className="me-1" />
                    Generating...
                  </>
                ) : (
                  '✨ Suggest Description with AI'
                )}
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

        <div className="d-flex gap-2">
          <Button variant="light" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="dark"
            type="submit"
            disabled={isAdding || !newCSV.description || (!newCSV.file && !newCSV.path)}
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
    sourceName: PropTypes.string
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
  onSubmit: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
  onFileChange: PropTypes.func.isRequired,
  onGenerateDescription: PropTypes.func.isRequired
};

export default AddCSVForm;
