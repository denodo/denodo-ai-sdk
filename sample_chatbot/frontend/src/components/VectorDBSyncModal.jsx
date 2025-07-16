import React, { useState, useEffect } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import axios from 'axios';

const VectorDBSyncModal = ({ show, syncTimeout, handleClose }) => {
  const [vdbs, setVdbs] = useState('');
  const [tags, setTags] = useState('');
  const [examplesPerTable, setExamplesPerTable] = useState(100);
  const [incremental, setIncremental] = useState(true);
  const [parallel, setParallel] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [hasCredentials, setHasCredentials] = useState(true);

  useEffect(() => {
    if (show) {
      // Check if credentials are available when modal is shown
      const checkConfig = async () => {
        try {
          const response = await axios.get('api/config');
          setHasCredentials(response.data.hasAISDKCredentials);
        } catch (error) {
          console.error('Error fetching config:', error);
          setHasCredentials(false);
        }
      };
      
      checkConfig();
    }
  }, [show]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setResponse(null);

    try {
      const response = await axios.post('sync_vdbs', {
        vdbs: vdbs.split(',').map(vdb => vdb.trim()).filter(vdb => vdb),
        tags: tags.split(',').map(tag => tag.trim()).filter(tag => tag),
        examples_per_table: examplesPerTable,
        incremental,
        parallel
      }, { timeout: syncTimeout });

      if (response.status === 204) {
        setResponse({
          success: true,
          message: "No Content: 204"
        });
      } else {
        setResponse({
          success: true,
          message: response.data.message
        });
      }
    } catch (error) {
      if (axios.isAxiosError(error) && error.code === 'ECONNABORTED') {
        setResponse({
          success: false,
          message: `The synchronization timeout has been exceeded (${syncTimeout}ms).`
        });
      } else {
        setResponse({
          success: false,
          message: error.response?.data?.message || 'An error occurred during synchronization.'
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleCloseAndReset = () => {
    setResponse(null);
    handleClose();
  };

  return (
    <Modal show={show} onHide={handleCloseAndReset}>
      <Modal.Header closeButton className="custom-header-modal">
        <Modal.Title>Sync VectorDB</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {!hasCredentials ? (
          <Alert variant="warning">
            AI SDK credentials are not configured. Please set the AI_SDK_USERNAME and AI_SDK_PASSWORD environment variables to use this feature.
          </Alert>
        ) : response ? (
          <div className="text-center">
            {response.success ? (
              <div className="d-flex flex-column align-items-center">
                <div className="text-success mb-3">
                  <i className="bi bi-check-circle-fill" style={{ fontSize: '3rem' }}></i>
                </div>
                <Alert variant="success">{response.message}</Alert>
              </div>
            ) : (
              <div className="d-flex flex-column align-items-center">
                <div className="text-danger mb-3">
                  <i className="bi bi-x-circle-fill" style={{ fontSize: '3rem' }}></i>
                </div>
                <Alert variant="danger">{response.message}</Alert>
              </div>
            )}
          </div>
        ) : (
          <Form onSubmit={handleSubmit}>
            <Form.Group className="mb-3">
              <Form.Label>VDBs to Sync (comma-separated)</Form.Label>
              <Form.Control
                type="text"
                placeholder="Specify a comma-separated list of VDBs to sync"
                value={vdbs}
                onChange={(e) => setVdbs(e.target.value)}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Tags to Sync (comma-separated)</Form.Label>
              <Form.Control
                type="text"
                placeholder="Specify a comma-separated list of tags to sync"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Examples per Table</Form.Label>
              <Form.Control
                type="number"
                min="0"
                value={examplesPerTable}
                onChange={(e) => setExamplesPerTable(parseInt(e.target.value))}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Enable incremental loading"
                checked={incremental}
                onChange={(e) => setIncremental(e.target.checked)}
              />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Check
                type="checkbox"
                label="Enable parallel processing"
                checked={parallel}
                onChange={(e) => setParallel(e.target.checked)}
              />
            </Form.Group>
            <Button variant="primary" type="submit" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Spinner
                    as="span"
                    animation="border"
                    size="sm"
                    role="status"
                    aria-hidden="true"
                  />
                  <span className="ms-2">Syncing...</span>
                </>
              ) : (
                'Sync'
              )}
            </Button>
          </Form>
        )}
      </Modal.Body>
    </Modal>
  );
};

export default VectorDBSyncModal; 