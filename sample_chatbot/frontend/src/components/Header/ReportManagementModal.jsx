import React from "react";
import Modal from "react-bootstrap/Modal";
import Button from "react-bootstrap/Button";
import Table from "react-bootstrap/Table";
import Badge from "react-bootstrap/Badge";
import Spinner from "react-bootstrap/Spinner";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import Tooltip from "react-bootstrap/Tooltip";
import { useReport, REPORT_STATUS } from "../../contexts/ReportContext";

const ReportManagementModal = () => {
  const { reports, isModalOpen, setIsModalOpen, removeReport, clearAllReports } = useReport();

  const getStatusBadge = (status) => {
    switch (status) {
      case REPORT_STATUS.PENDING:
        return <Badge bg="secondary">Pending</Badge>;
      case REPORT_STATUS.PROCESSING:
        return (
          <Badge bg="warning" text="dark" className="d-flex align-items-center">
            <Spinner size="sm" animation="border" className="me-1" />
            Processing
          </Badge>
        );
      case REPORT_STATUS.COMPLETED:
        return <Badge bg="success">Completed</Badge>;
      case REPORT_STATUS.FAILED:
        return <Badge bg="danger">Failed</Badge>;
      default:
        return <Badge bg="secondary">Unknown</Badge>;
    }
  };

  const formatDate = (date) => {
    return new Date(date).toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  const handleDownload = (report) => {
    if (report.downloadUrl) {
      const link = document.createElement('a');
      link.href = report.downloadUrl;
      const defaultFilename = report.reportTitle 
        ? `${report.reportTitle.trim().replace(/[/\\?%*:|"<>]/g, '').replace(/\s+/g, '_')}_report.html`
        : `${report.id}_report.html`;
      link.download = report.filename || defaultFilename;
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
    >
      <Modal.Header closeButton data-bs-theme="light">
        <Modal.Title>DeepQuery Reports</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {reports.length === 0 ? (
          <div className="text-center py-4">
            <p>No reports generated yet. Use DeepQuery to generate a report.</p>
          </div>
        ) : (
          <>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h6 className="mb-0">
                Total: {reports.length} report{reports.length !== 1 ? 's' : ''}
              </h6>
              {reports.length > 0 && (
                <Button 
                  variant="outline-danger" 
                  size="sm"
                  onClick={clearAllReports}
                >
                  Clear All
                </Button>
              )}
            </div>
            
            <Table striped bordered hover variant="light" className="table-responsive align-middle">
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>Report Title</th>
                  <th style={{ width: '10%' }}>Language</th>
                  <th style={{ width: '15%' }}>Status</th>
                  <th style={{ width: '15%' }}>Requested</th>
                  <th style={{ width: '15%' }}>Generated</th>
                  <th style={{ width: '15%' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((report) => (
                  <tr key={report.id}>
                    <td>
                      <div style={{ maxWidth: '400px' }}>
                        <OverlayTrigger
                          placement="top"
                          overlay={renderTooltip(report.reportTitle || report.question)}
                        >
                          <span className="text-truncate d-block fw-medium">
                            {report.reportTitle || report.question}
                          </span>
                        </OverlayTrigger>
                      </div>
                    </td>
                    <td>
                      <div style={{ maxWidth: '120px' }}>
                        <OverlayTrigger
                          placement="top"
                          overlay={renderTooltip(report.language || 'English')}
                        >
                          <Badge
                            bg="light"
                            text="dark"
                            className="border border-secondary-subtle text-truncate"
                            style={{ maxWidth: '100%' }}
                          >
                            {report.language || 'English'}
                          </Badge>
                        </OverlayTrigger>
                      </div>
                    </td>
                    <td>
                      {getStatusBadge(report.status)}
                      {report.error && (
                        <OverlayTrigger
                          placement="top"
                          overlay={renderTooltip(report.error)}
                        >
                          <i className="bi bi-exclamation-triangle-fill text-warning ms-2"></i>
                        </OverlayTrigger>
                      )}
                    </td>
                    <td>
                      <small className="text-muted">{formatDate(report.createdAt)}</small>
                    </td>
                    <td>
                      <small className="text-muted">
                        {report.completedAt ? formatDate(report.completedAt) : '-'}
                      </small>
                    </td>
                    <td>
                      <div className="d-flex gap-1">
                        {report.status === REPORT_STATUS.COMPLETED && (
                          <OverlayTrigger
                            placement="top"
                            overlay={renderTooltip("Download report")}
                          >
                            <Button
                              variant="success"
                              size="sm"
                              onClick={() => handleDownload(report)}
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
                            onClick={() => removeReport(report.id)}
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
                <strong>Note:</strong> Reports are generated asynchronously and will be available for download once completed.
                Failed reports can be removed from the list.
              </small>
            </div>
          </>
        )}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="light" onClick={handleClose}>
          Close
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default ReportManagementModal;
