import React, { useState, useEffect } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Tabs from 'react-bootstrap/Tabs';
import Tab from 'react-bootstrap/Tab';
import axios from 'axios';

const VectorDBSyncModal = ({ show, syncTimeout, handleClose }) => {
  // Common state
  const [activeTab, setActiveTab] = useState('sync');
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [hasCredentials, setHasCredentials] = useState(true);

  // Sync state
  const [syncVdbs, setSyncVdbs] = useState('');
  const [syncTags, setSyncTags] = useState('');
  const [ignoreTags, setIgnoreTags] = useState('');
  const [examplesPerTable, setExamplesPerTable] = useState(100);
  const [incremental, setIncremental] = useState(true);
  const [parallel, setParallel] = useState(true);

  // Delete state
  const [deleteVdbs, setDeleteVdbs] = useState('');
  const [deleteTags, setDeleteTags] = useState('');
  const [deleteConflicting, setDeleteConflicting] = useState(false);

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

  const handleSyncSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setResponse(null);

    try {
      const response = await axios.post('sync_vdbs', {
        vdbs: syncVdbs.split(',').map(vdb => vdb.trim()).filter(vdb => vdb),
        tags: syncTags.split(',').map(tag => tag.trim()).filter(tag => tag),
        tags_to_ignore: ignoreTags.split(',').map(tag => tag.trim()).filter(tag => tag),
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
  
  const handleDeleteSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setResponse(null);

    try {
        const response = await axios.delete('delete_metadata', {
            data: {
                vdp_database_names: deleteVdbs,
                vdp_tag_names: deleteTags,
                delete_conflicting: deleteConflicting
            }
        });

        if (response.status === 204) {
            setResponse({
                success: true,
                message: "No Content: No metadata found matching the specified criteria for deletion."
            });
        } else {
            setResponse({
                success: true,
                message: response.data.message
            });
        }
    } catch (error) {
        setResponse({
            success: false,
            message: error.response?.data?.message || 'An error occurred during deletion.'
        });
    } finally {
        setIsLoading(false);
    }
  };

  const handleCloseAndReset = () => {
    setResponse(null);
    setActiveTab('sync');
    // Reset sync form
    setSyncVdbs('');
    setSyncTags('');
    setIgnoreTags('');
    // Reset delete form
    setDeleteVdbs('');
    setDeleteTags('');
    setDeleteConflicting(false);
    handleClose();
  };

  return (
    <Modal show={show} onHide={handleCloseAndReset} style={{ '--bs-modal-bg': '#112533' }} contentClassName="text-white border border-white">
      <Modal.Header closeButton className="custom-header-modal">
        <Modal.Title>VectorDB Management</Modal.Title>
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
          <Tabs activeKey={activeTab} onSelect={(k) => setActiveTab(k)} id="vdb-management-tabs" className="mb-3">
            <Tab eventKey="sync" title="Sync">
              <Form onSubmit={handleSyncSubmit}>
                <Form.Group className="mb-3">
                  <Form.Label>VDBs to Sync (comma-separated)</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="Specify a comma-separated list of VDBs to sync"
                    value={syncVdbs}
                    onChange={(e) => setSyncVdbs(e.target.value)}
                  />
                </Form.Group>
                <Form.Group className="mb-3">
                  <Form.Label>Tags to Sync (comma-separated)</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="Specify a comma-separated list of tags to sync"
                    value={syncTags}
                    onChange={(e) => setSyncTags(e.target.value)}
                  />
                </Form.Group>
                <Form.Group className="mb-3">
                  <Form.Label>Tags to ignore (comma-separated)</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="Specify a comma-separated list of tags to ignore"
                    value={ignoreTags}
                    onChange={(e) => setIgnoreTags(e.target.value)}
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
                <Button variant="primary" type="submit" disabled={isLoading} style={{ backgroundColor: '#2D3E4B', borderColor: '#2D3E4B' }}>
                  {isLoading ? (
                    <>
                      <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
                      <span className="ms-2">Syncing...</span>
                    </>
                  ) : ( 'Sync' )}
                </Button>
              </Form>
            </Tab>
            <Tab eventKey="delete" title="Delete">
              <Form onSubmit={handleDeleteSubmit}>
                <Form.Group className="mb-3">
                  <Form.Label>VDBs to Delete (comma-separated)</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="Leave empty to ignore, or list VDBs"
                    value={deleteVdbs}
                    onChange={(e) => setDeleteVdbs(e.target.value)}
                  />
                </Form.Group>
                <Form.Group className="mb-3">
                  <Form.Label>Tags to Delete (comma-separated)</Form.Label>
                  <Form.Control
                    type="text"
                    placeholder="Leave empty to ignore, or list tags"
                    value={deleteTags}
                    onChange={(e) => setDeleteTags(e.target.value)}
                  />
                  <Form.Text className="text-white">
                    At least one VDB or tag must be provided.
                  </Form.Text>
                </Form.Group>
                <Form.Group className="mb-3">
                  <Form.Check
                    type="checkbox"
                    label="Delete conflicting entries"
                    checked={deleteConflicting}
                    onChange={(e) => setDeleteConflicting(e.target.checked)}
                  />
                   <Form.Text className="text-white">
                    If unchecked, entries linked to other synchronized sources will be preserved.
                  </Form.Text>
                </Form.Group>
                <Button variant="danger" type="submit" disabled={isLoading}>
                  {isLoading ? (
                    <>
                      <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
                      <span className="ms-2">Deleting...</span>
                    </>
                  ) : ( 'Delete' )}
                </Button>
              </Form>
            </Tab>
          </Tabs>
        )}
      </Modal.Body>
    </Modal>
  );
};

export default VectorDBSyncModal;