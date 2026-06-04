import React from 'react';
import PropTypes from 'prop-types';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Badge from 'react-bootstrap/Badge';

const ScannedFileRow = ({ scannedFile, onAdd }) => {
  return (
    <tr style={{ backgroundColor: '#fff9e6', verticalAlign: 'middle' }}>
      <td className="text-center">
        <Form.Check type="switch" checked={false} disabled title="Add this source first" />
      </td>
      <td style={{ maxWidth: '260px', overflowWrap: 'anywhere', wordBreak: 'break-word' }}>
        <strong>{scannedFile.source_name}</strong>
      </td>
      <td>
        <Badge bg="warning" text="dark">
          <i className="bi bi-radar me-1" />Scanned
        </Badge>
      </td>
      <td style={{ fontSize: '0.85em' }}>
        <span className="text-muted fst-italic">Not yet vectorized</span>
      </td>
      <td className="text-center text-muted" style={{ fontSize: '0.85em' }}>—</td>
      <td className="text-center text-muted" style={{ fontSize: '0.85em' }}>—</td>
      <td>
        <Button variant="outline-primary" size="sm" onClick={() => onAdd(scannedFile)}>
          Add
        </Button>
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
