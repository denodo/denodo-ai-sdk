import React from 'react';
import PropTypes from 'prop-types';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Badge from 'react-bootstrap/Badge';
import Spinner from 'react-bootstrap/Spinner';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';

const formatDate = (ms) => {
  if (!ms) return '—';
  const d = new Date(typeof ms === 'number' ? ms : Number(ms));
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit'
  });
};

const SourceRow = ({
  source,
  currentUsername,
  editingSource,
  editingDescription,
  onDelete,
  isDeleting,
  onDownload,
  isDownloading,
  onTogglePrivate,
  isTogglingPrivate,
  onStartEditing,
  onUpdateDescription,
  onCancelEditing,
  setEditingDescription
}) => {
  const isEditing = editingSource === source.source_name;
  const hasDescription = Boolean(source.description?.trim());
  const isOwner = source.is_owner ?? (source.owner && source.owner === currentUsername);
  const isPrivate = Boolean(source.private);
  // Capability flags come from the server; fall back to legacy logic for safety.
  const canSubscribe = source.can_subscribe ?? !isPrivate ?? isOwner;
  const canDelete = source.can_delete ?? isOwner;
  const canEdit = source.can_edit ?? isOwner;
  const canMakePublic = source.can_make_public ?? false;
  const canMakePrivate = source.can_make_private ?? isOwner;
  // The lock/unlock button: show only when the user can change visibility in
  // the direction the click would take it.
  const canTogglePrivacy = isPrivate ? canMakePublic : canMakePrivate;

  return (
    <tr style={{ verticalAlign: 'middle' }}>
      <td style={{ maxWidth: '260px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
        <strong>{source.source_name}</strong>
        {source.document_count ? (
          <span className="text-muted ms-1" style={{ fontSize: '0.8em' }}>
            ({source.document_count} rows)
          </span>
        ) : null}
      </td>
      <td>
        <div className="d-flex flex-wrap gap-1">
          {isPrivate ? (
            <OverlayTrigger placement="top" overlay={<Tooltip>Visible only to you</Tooltip>}>
              <Badge bg="dark"><i className="bi bi-lock-fill me-1" />Private</Badge>
            </OverlayTrigger>
          ) : (
            <OverlayTrigger placement="top" overlay={<Tooltip>Any user in this chatbot can have access to this knowledge base</Tooltip>}>
              <Badge bg="success"><i className="bi bi-globe2 me-1" />Public</Badge>
            </OverlayTrigger>
          )}
          {source.agent_managed && (
            <OverlayTrigger placement="top" overlay={<Tooltip>Declared in the agent's configuration — always active for every user of this agent</Tooltip>}>
              <Badge bg="primary"><i className="bi bi-robot me-1" />Agent</Badge>
            </OverlayTrigger>
          )}
          {!source.path_valid && (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip>Original CSV file is gone, but vectors are still searchable.</Tooltip>}
            >
              <Badge bg="warning" text="dark" style={{ cursor: 'help' }}>
                <i className="bi bi-exclamation-triangle-fill me-1" />file missing
              </Badge>
            </OverlayTrigger>
          )}
        </div>
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
              <Button variant="dark" size="sm" onClick={() => onUpdateDescription(source.source_name)}>Save</Button>
              <Button variant="light" size="sm" onClick={onCancelEditing}>Cancel</Button>
            </div>
          </div>
        ) : (
          <div
            onDoubleClick={() => canEdit && onStartEditing(source)}
            style={{ cursor: canEdit ? 'pointer' : 'default' }}
            title={canEdit ? 'Double-click to edit' : 'Only the owner can edit the description'}
          >
            {source.description?.substring(0, 100)}
            {source.description?.length > 100 ? '...' : ''}
            {!hasDescription && (
              <span className="text-warning fst-italic">No description</span>
            )}
          </div>
        )}
      </td>
      <td className="text-center" style={{ fontSize: '0.85em' }}>
        {source.owner ? (
          <span className="text-muted">{source.owner}</span>
        ) : (
          <span className="text-muted">—</span>
        )}
      </td>
      <td className="text-center text-muted" style={{ fontSize: '0.8em' }}>
        {formatDate(source.last_vectorized)}
      </td>
      <td>
        <div className="d-flex gap-1 flex-wrap">
          {canSubscribe && (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip>{isDownloading ? 'Preparing CSV…' : 'Download CSV with embedding column'}</Tooltip>}
            >
              <Button
                variant="outline-success"
                size="sm"
                onClick={() => onDownload(source.source_name)}
                disabled={isDownloading}
              >
                {isDownloading ? (
                  <Spinner animation="border" size="sm" role="status" aria-label="Downloading" />
                ) : (
                  <i className="bi bi-download" />
                )}
              </Button>
            </OverlayTrigger>
          )}
          {canTogglePrivacy && (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip>
                {isTogglingPrivate
                  ? 'Updating visibility…'
                  : isPrivate
                    ? 'Publish (admin only)'
                    : 'Make private (only you can see it)'}
              </Tooltip>}
            >
              <Button
                variant={isPrivate ? 'outline-dark' : 'outline-secondary'}
                size="sm"
                onClick={() => onTogglePrivate(source.source_name, !isPrivate)}
                disabled={isTogglingPrivate || isDeleting}
              >
                {isTogglingPrivate ? (
                  <Spinner animation="border" size="sm" role="status" aria-label="Updating visibility" />
                ) : (
                  <i className={`bi ${isPrivate ? 'bi-unlock' : 'bi-lock'}`} />
                )}
              </Button>
            </OverlayTrigger>
          )}
          {canDelete && (
            <Button
              variant="outline-danger"
              size="sm"
              onClick={() => onDelete(source.source_name, false)}
              disabled={isDeleting || isTogglingPrivate}
              title={isOwner ? '' : 'Admin: delete this collection'}
            >
              {isDeleting ? (
                <>
                  <Spinner animation="border" size="sm" role="status" className="me-1" aria-label="Deleting" />
                  Deleting…
                </>
              ) : 'Delete'}
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
};

SourceRow.propTypes = {
  source: PropTypes.shape({
    source_name: PropTypes.string.isRequired,
    active: PropTypes.bool.isRequired,
    description: PropTypes.string,
    path_valid: PropTypes.bool,
    owner: PropTypes.string,
    is_owner: PropTypes.bool,
    document_count: PropTypes.number,
    vectorized_columns: PropTypes.arrayOf(PropTypes.string),
    last_vectorized: PropTypes.number,
    private: PropTypes.bool,
    can_subscribe: PropTypes.bool,
    can_delete: PropTypes.bool,
    can_edit: PropTypes.bool,
    can_make_public: PropTypes.bool,
    can_make_private: PropTypes.bool
  }).isRequired,
  currentUsername: PropTypes.string,
  editingSource: PropTypes.string,
  editingDescription: PropTypes.string.isRequired,
  onDelete: PropTypes.func.isRequired,
  isDeleting: PropTypes.bool,
  onDownload: PropTypes.func.isRequired,
  isDownloading: PropTypes.bool,
  onTogglePrivate: PropTypes.func.isRequired,
  isTogglingPrivate: PropTypes.bool,
  onStartEditing: PropTypes.func.isRequired,
  onUpdateDescription: PropTypes.func.isRequired,
  onCancelEditing: PropTypes.func.isRequired,
  setEditingDescription: PropTypes.func.isRequired
};

export default SourceRow;
