import React from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Table from 'react-bootstrap/Table';
import Badge from 'react-bootstrap/Badge';
import Spinner from 'react-bootstrap/Spinner';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';
import { usePDF, PDF_STATUS } from '../contexts/PDFContext';

const PDFManagementModal = () => {
  const { pdfs, isModalOpen, setIsModalOpen, removePDF, clearAllPDFs } = usePDF();

  const getStatusBadge = (status) => {
    switch (status) {
      case PDF_STATUS.PENDING:
        return <Badge bg="secondary">Pending</Badge>;
      case PDF_STATUS.PROCESSING:
        return (
          <Badge bg="warning" text="dark" className="d-flex align-items-center">
            <Spinner size="sm" animation="border" className="me-1" />
            Processing
          </Badge>
        );
      case PDF_STATUS.COMPLETED:
        return <Badge bg="success">Completed</Badge>;
      case PDF_STATUS.FAILED:
        return <Badge bg="danger">Failed</Badge>;
      default:
        return <Badge bg="secondary">Unknown</Badge>;
    }
  };

  const formatDate = (date) => {
    return new Date(date).toLocaleString();
  };

  const handleDownload = (pdf) => {
    if (pdf.downloadUrl) {
      const link = document.createElement('a');
      link.href = pdf.downloadUrl;
      // Use the filename from the server if available, otherwise create one from report title
      const defaultFilename = pdf.reportTitle 
        ? `${pdf.reportTitle.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_report.pdf`
        : `${pdf.id}_report.pdf`;
      link.download = pdf.filename || defaultFilename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  const handleClose = () => {
    setIsModalOpen(false);
  };

  const renderTooltip = (content) => (
    <Tooltip>{content}</Tooltip>
  );

  return (
    <Modal 
      show={isModalOpen} 
      onHide={handleClose} 
      size="xl" 
      centered
      style={{ '--bs-modal-bg': '#112533' }}
      contentClassName="text-white border border-white"
    >
      <Modal.Header closeButton className="border-bottom border-white">
        <Modal.Title>DeepQuery Reports</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {pdfs.length === 0 ? (
          <div className="text-center py-4">
            <p>No PDF reports generated yet. Use the DeepQuery button to generate a report.</p>
          </div>
        ) : (
          <>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h6 className="mb-0">
                Total: {pdfs.length} report{pdfs.length !== 1 ? 's' : ''}
              </h6>
              {pdfs.length > 0 && (
                <Button 
                  variant="outline-danger" 
                  size="sm"
                  onClick={clearAllPDFs}
                >
                  Clear All
                </Button>
              )}
            </div>
            
            <Table striped bordered hover variant="dark" className="table-responsive">
              <thead>
                <tr>
                  <th style={{ width: '40%' }}>Report Title</th>
                  <th style={{ width: '15%' }}>Status</th>
                  <th style={{ width: '15%' }}>Requested</th>
                  <th style={{ width: '15%' }}>Generated</th>
                  <th style={{ width: '15%' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pdfs.map((pdf) => (
                  <tr key={pdf.id}>
                    <td>
                      <div style={{ maxWidth: '500px' }}>
                        <OverlayTrigger
                          placement="top"
                          overlay={renderTooltip(pdf.reportTitle || pdf.question)}
                        >
                          <span className="text-truncate d-block">
                            {pdf.reportTitle || pdf.question}
                          </span>
                        </OverlayTrigger>
                      </div>
                    </td>
                    <td>
                      {getStatusBadge(pdf.status)}
                      {pdf.error && (
                        <OverlayTrigger
                          placement="top"
                          overlay={renderTooltip(pdf.error)}
                        >
                          <i className="bi bi-exclamation-triangle-fill text-warning ms-2"></i>
                        </OverlayTrigger>
                      )}
                    </td>
                    <td>
                      <small>{formatDate(pdf.createdAt)}</small>
                    </td>
                    <td>
                      <small>
                        {pdf.completedAt ? formatDate(pdf.completedAt) : '-'}
                      </small>
                    </td>
                    <td>
                      <div className="d-flex gap-1">
                        {pdf.status === PDF_STATUS.COMPLETED && (
                          <OverlayTrigger
                            placement="top"
                            overlay={renderTooltip("Download PDF")}
                          >
                            <Button
                              variant="success"
                              size="sm"
                              onClick={() => handleDownload(pdf)}
                            >
                              <i className="bi bi-download"></i>
                            </Button>
                          </OverlayTrigger>
                        )}
                        <OverlayTrigger
                          placement="top"
                          overlay={renderTooltip("Remove from list")}
                        >
                          <Button
                            variant="outline-danger"
                            size="sm"
                            onClick={() => removePDF(pdf.id)}
                          >
                            <i className="bi bi-trash"></i>
                          </Button>
                        </OverlayTrigger>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
            
            <div className="mt-3">
              <small className="text-muted">
                <strong>Note:</strong> PDFs are generated asynchronously and will be available for download once completed.
                Failed PDFs can be removed from the list.
              </small>
            </div>
          </>
        )}
      </Modal.Body>
      <Modal.Footer className="border-top border-white">
        <Button variant="secondary" onClick={handleClose} style={{ backgroundColor: '#2D3E4B', borderColor: '#2D3E4B' }}>
          Close
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default PDFManagementModal; 