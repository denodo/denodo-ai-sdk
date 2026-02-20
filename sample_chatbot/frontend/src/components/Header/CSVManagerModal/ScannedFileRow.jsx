import React from 'react';
import PropTypes from 'prop-types';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Badge from 'react-bootstrap/Badge';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Popover from 'react-bootstrap/Popover';

const ScannedFileRow = ({ scannedFile, onAdd }) => {
  return (
    <tr style={{ backgroundColor: '#fff9e6' }}>
      <td className="text-center">
        <Form.Check type="switch" checked={false} disabled title="Add this source first" />
      </td>
      <td>
        <strong>{scannedFile.source_name}</strong>
        <OverlayTrigger
          trigger="click"
          placement="right"
          rootClose
          overlay={
            <Popover>
              <Popover.Header as="h3">File Path</Popover.Header>
              <Popover.Body style={{ fontSize: '0.8em', wordBreak: 'break-all' }}>
                {scannedFile.path}
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
        <span className="text-muted fst-italic">-</span>
      </td>
      <td className="text-center">
        <Badge bg="warning" text="dark">
          Scanned
        </Badge>
      </td>
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
