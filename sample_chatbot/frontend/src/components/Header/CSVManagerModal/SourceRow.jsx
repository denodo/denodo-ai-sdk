import React from 'react';
import PropTypes from 'prop-types';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Badge from 'react-bootstrap/Badge';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Popover from 'react-bootstrap/Popover';
import Tooltip from 'react-bootstrap/Tooltip';

const SourceRow = ({
  source,
  editingSource,
  editingDescription,
  onToggleActive,
  onDelete,
  onStartEditing,
  onUpdateDescription,
  onCancelEditing,
  setEditingDescription
}) => {
  const isEditing = editingSource === source.source_name;
  const hasDescription = Boolean(source.description?.trim());

  return (
    <tr>
      <td className="text-center">
        <Form.Check
          type="switch"
          checked={source.active}
          onChange={() => onToggleActive(source.source_name, source.active)}
          disabled={!hasDescription}
          title={hasDescription ? '' : 'Add a description to enable'}
        />
      </td>
      <td>
        <strong>{source.source_name}</strong>
        <OverlayTrigger
          trigger="click"
          placement="right"
          rootClose
          overlay={
            <Popover>
              <Popover.Header as="h3">File Path</Popover.Header>
              <Popover.Body style={{ fontSize: '0.8em', wordBreak: 'break-all' }}>
                {source.path}
              </Popover.Body>
            </Popover>
          }
        >
          <Button variant="link" size="sm" className="p-0 ms-2" title="Show file path">
            <i className="bi bi-info-circle text-secondary"></i>
          </Button>
        </OverlayTrigger>
      </td>
      <td style={{ fontSize: '0.85em' }}>
        {isEditing ? (
          <div className="d-flex flex-column gap-1">
            <Form.Control
              as="textarea"
              rows={2}
              size="sm"
              value={editingDescription}
              onChange={(e) => setEditingDescription(e.target.value)}
              autoFocus
            />
            <div className="d-flex gap-1">
              <Button
                variant="dark"
                size="sm"
                onClick={() => onUpdateDescription(source.source_name)}
              >
                Save
              </Button>
              <Button variant="light" size="sm" onClick={onCancelEditing}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div
            onDoubleClick={() => onStartEditing(source)}
            style={{ cursor: 'pointer' }}
            title="Double-click to edit"
          >
            {source.description?.substring(0, 100)}
            {source.description?.length > 100 ? '...' : ''}
            {!hasDescription && (
              <span className="text-warning fst-italic">No description - click to add</span>
            )}
          </div>
        )}
      </td>
      <td className="text-center">
        {source.path_valid ? (
          <Badge bg="success">Valid</Badge>
        ) : (
          <OverlayTrigger
            placement="top"
            overlay={
              <Tooltip>
                CSV file not found in original path, but documents still exist in the vectorDB and are usable.
              </Tooltip>
            }
          >
            <Badge bg="warning" text="dark" style={{ cursor: 'help' }}>
              File Missing
            </Badge>
          </OverlayTrigger>
        )}
      </td>
      <td>
        <Button
          variant="outline-danger"
          size="sm"
          onClick={() => onDelete(source.source_name, false)}
        >
          Delete
        </Button>
      </td>
    </tr>
  );
};

SourceRow.propTypes = {
  source: PropTypes.shape({
    source_name: PropTypes.string.isRequired,
    active: PropTypes.bool.isRequired,
    description: PropTypes.string,
    path: PropTypes.string.isRequired,
    path_valid: PropTypes.bool.isRequired
  }).isRequired,
  editingSource: PropTypes.string,
  editingDescription: PropTypes.string.isRequired,
  onToggleActive: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired,
  onStartEditing: PropTypes.func.isRequired,
  onUpdateDescription: PropTypes.func.isRequired,
  onCancelEditing: PropTypes.func.isRequired,
  setEditingDescription: PropTypes.func.isRequired
};

export default SourceRow;
