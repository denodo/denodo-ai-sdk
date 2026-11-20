import React from 'react';
import PropTypes from 'prop-types';
import Form from 'react-bootstrap/Form';
import Spinner from 'react-bootstrap/Spinner';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';

const OVERLAY_PROPS = { container: () => document.body, popperConfig: { strategy: 'fixed' } };

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
  const canSubscribe = source.can_subscribe ?? !isPrivate ?? isOwner;
  const canDelete = source.can_delete ?? isOwner;
  const canEdit = source.can_edit ?? isOwner;
  const canMakePublic = source.can_make_public ?? false;
  const canMakePrivate = source.can_make_private ?? isOwner;
  const canTogglePrivacy = isPrivate ? canMakePublic : canMakePrivate;

  return (
    <tr>
      <td style={{ maxWidth: '260px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
        <span className="skm-code-badge">{source.source_name}</span>
        {source.document_count ? (
          <span className="text-muted ms-2 small">
            ({source.document_count} rows)
          </span>
        ) : null}
      </td>

      <td>
        <div className="d-flex flex-wrap gap-1 align-items-center">
          {isPrivate ? (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip id={`tip-priv-${source.source_name}`}>Visible only to you</Tooltip>}
              {...OVERLAY_PROPS}
            >
              <span className="rcc-badge rcc-badge-personal">
                <i className="bi bi-lock-fill" />
                Private
              </span>
            </OverlayTrigger>
          ) : (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip id={`tip-pub-${source.source_name}`}>Any user in this chatbot can have access to this knowledge base</Tooltip>}
              {...OVERLAY_PROPS}
            >
              <span className="rcc-badge rcc-badge-system">
                <i className="bi bi-globe2" />
                Public
              </span>
            </OverlayTrigger>
          )}

          {source.agent_managed && (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip id={`tip-agent-${source.source_name}`}>Declared in the agent's configuration — always active for every user of this agent</Tooltip>}
              {...OVERLAY_PROPS}
            >
              <span className="rcc-badge rcc-badge-personal">
                <i className="bi bi-robot" />
                Agent
              </span>
            </OverlayTrigger>
          )}

          {!source.path_valid && (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip id={`tip-missing-${source.source_name}`}>Original CSV file is gone, but vectors are still searchable.</Tooltip>}
              {...OVERLAY_PROPS}
            >
              <span className="rcc-badge rcc-badge-error">
                <i className="bi bi-exclamation-triangle-fill" />
                File missing
              </span>
            </OverlayTrigger>
          )}
        </div>
      </td>

      <td>
        {isEditing ? (
          <div className="d-flex flex-column gap-2 p-1">
            <Form.Control
              as="textarea"
              rows={2}
              size="sm"
              value={editingDescription}
              onChange={(e) => setEditingDescription(e.target.value)}
              autoFocus
              className="skm-input"
            />
            <div className="d-flex gap-2">
              <button
                type="button"
                className="rcc-light-btn"
                style={{ height: '28px', padding: '0 0.65rem', fontSize: '0.78rem' }}
                onClick={() => onUpdateDescription(source.source_name)}
              >
                Save
              </button>
              <button
                type="button"
                className="rcc-ghost-btn"
                style={{ height: '28px', padding: '0 0.65rem', fontSize: '0.78rem' }}
                onClick={onCancelEditing}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div
            className="small text-secondary"
            onDoubleClick={() => canEdit && onStartEditing(source)}
            style={{ cursor: canEdit ? 'pointer' : 'default' }}
            title={canEdit ? 'Double-click to edit description' : 'Only the owner can edit the description'}
          >
            {hasDescription ? (
              <>
                {source.description.substring(0, 100)}
                {source.description.length > 100 ? '...' : ''}
              </>
            ) : (
              <em className="text-muted">No description</em>
            )}
          </div>
        )}
      </td>

      <td>
        <span className="small text-secondary">
          {source.owner || '—'}
        </span>
      </td>

      <td>
        <span className="small text-muted">
          {formatDate(source.last_vectorized)}
        </span>
      </td>

      <td>
        <div className="d-flex align-items-center gap-1">
          {canSubscribe && (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip id={`tip-dl-${source.source_name}`}>{isDownloading ? 'Preparing CSV…' : 'Download CSV'}</Tooltip>}
              {...OVERLAY_PROPS}
            >
              <button
                type="button"
                className="rcc-icon-btn"
                onClick={() => onDownload(source.source_name)}
                disabled={isDownloading}
                aria-label="Download CSV"
              >
                {isDownloading ? (
                  <Spinner animation="border" size="sm" />
                ) : (
                  <i className="bi bi-download" />
                )}
              </button>
            </OverlayTrigger>
          )}

          {canTogglePrivacy && (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip id={`tip-priv-toggle-${source.source_name}`}>
                {isTogglingPrivate
                  ? 'Updating visibility…'
                  : isPrivate
                    ? 'Publish (admin only)'
                    : 'Make private (only you can see it)'}
              </Tooltip>}
              {...OVERLAY_PROPS}
            >
              <button
                type="button"
                className="rcc-icon-btn"
                onClick={() => onTogglePrivate(source.source_name, !isPrivate)}
                disabled={isTogglingPrivate || isDeleting}
                aria-label={isPrivate ? 'Publish' : 'Make private'}
              >
                {isTogglingPrivate ? (
                  <Spinner animation="border" size="sm" />
                ) : (
                  <i className={`bi ${isPrivate ? 'bi-unlock' : 'bi-lock'}`} />
                )}
              </button>
            </OverlayTrigger>
          )}

          {canDelete && (
            <OverlayTrigger
              placement="top"
              overlay={<Tooltip id={`tip-del-${source.source_name}`}>{isOwner ? 'Delete collection' : 'Admin: delete collection'}</Tooltip>}
              {...OVERLAY_PROPS}
            >
              <button
                type="button"
                className="rcc-icon-btn rcc-icon-btn-danger"
                onClick={() => onDelete(source.source_name, false)}
                disabled={isDeleting || isTogglingPrivate}
                aria-label="Delete collection"
              >
                {isDeleting ? (
                  <Spinner animation="border" size="sm" />
                ) : (
                  <i className="bi bi-trash" />
                )}
              </button>
            </OverlayTrigger>
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
    agent_managed: PropTypes.bool,
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
