import React from 'react';
import PropTypes from 'prop-types';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';

const OVERLAY_PROPS = { container: () => document.body, popperConfig: { strategy: 'fixed' } };

const ScannedFileRow = ({ scannedFile, onAdd }) => {
  return (
    <tr style={{ backgroundColor: '#fffdf5' }}>
      <td style={{ maxWidth: '260px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
        <span className="skm-code-badge">{scannedFile.source_name}</span>
      </td>

      <td>
        <span className="rcc-badge rcc-badge-warning">
          <i className="bi bi-radar" />
          Scanned
        </span>
      </td>

      <td>
        <span className="small text-muted fst-italic">Not yet vectorized</span>
      </td>

      <td>
        <span className="small text-muted">—</span>
      </td>

      <td>
        <span className="small text-muted">—</span>
      </td>

      <td>
        <div className="d-flex align-items-center">
          <OverlayTrigger
            placement="top"
            overlay={<Tooltip id={`tip-add-${scannedFile.source_name}`}>Add scanned CSV</Tooltip>}
            {...OVERLAY_PROPS}
          >
            <button
              type="button"
              className="rcc-icon-btn"
              onClick={() => onAdd(scannedFile)}
              aria-label="Add scanned file"
            >
              <i className="bi bi-plus-circle" />
            </button>
          </OverlayTrigger>
        </div>
      </td>
    </tr>
  );
};

ScannedFileRow.propTypes = {
  scannedFile: PropTypes.shape({
    source_name: PropTypes.string.isRequired,
    path: PropTypes.string.isRequired
  }).isRequired,
  onAdd: PropTypes.func.isRequired
};

export default ScannedFileRow;
