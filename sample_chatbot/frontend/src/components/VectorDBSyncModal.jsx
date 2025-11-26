import React, { useState, useEffect } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Tabs from 'react-bootstrap/Tabs';
import Tab from 'react-bootstrap/Tab';
import ListGroup from 'react-bootstrap/ListGroup';
import axios from 'axios';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';
import NotificationToast from './NotificationToast/NotificationToast'; 

const formatTimestamp = (timestamp) => {
  if (!timestamp) return 'N/A';
  try {
    const date = new Date(timestamp);
    const options = {
      dateStyle: 'short',
      timeStyle: 'short'
    };
    return date.toLocaleString(undefined, options);
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return 'Invalid Date';
  }
};

const VectorDBSyncModal = ({ show, syncTimeout, handleClose, syncedResources, onSyncUpdate }) => {
  // Common state
  const [activeTab, setActiveTab] = useState('status');
  const [isLoading, setIsLoading] = useState(false);
  const [hasCredentials, setHasCredentials] = useState(true);
  const [statusData, setStatusData] = useState(syncedResources || {});

  // Toast State
  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: '',
    variant: 'info',
    title: '',
    duration: 5000
  });

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
      if (!isLoading) {
        setStatusData(syncedResources || {});
      }

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
  }, [show, syncedResources, isLoading]);

  const showToast = (message, variant, title, duration = 5000) => {
    setToastConfig({ show: true, message, variant, title, duration });
  };

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const checkResourcesAlreadyExist = (requestedVdbs, requestedTags) => {
    const existingVdbs = statusData?.DATABASE ? Object.keys(statusData.DATABASE) : [];
    const existingTags = statusData?.TAG ? Object.keys(statusData.TAG) : [];
    
    return requestedVdbs.some(vdb => existingVdbs.includes(vdb)) || 
           requestedTags.some(tag => existingTags.includes(tag));
  };

  const handleSyncSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);

    const processedVdbs = syncVdbs.split(',').map(vdb => vdb.trim()).filter(vdb => vdb);
    const processedTags = syncTags.split(',').map(tag => tag.trim()).filter(tag => tag);
    const processedIgnoreTags = ignoreTags.split(',').map(tag => tag.trim()).filter(tag => tag);

    try {
      const response = await axios.post('sync_vdbs', {
        vdbs: processedVdbs,
        tags: processedTags,
        tags_to_ignore: processedIgnoreTags,
        examples_per_table: examplesPerTable,
        incremental,
        parallel
      }, { timeout: syncTimeout });

      if (response.status === 204) {
        if (incremental) {
            const existsLocally = checkResourcesAlreadyExist(processedVdbs, processedTags);
            if (existsLocally) {
                showToast(
                    "You made an incremental request, but no updates have been made to the desired data since the last sync.",
                    "warning",
                    "No Updates",
                    10000
                );
            } else {
                showToast(
                    "The selected databases/tags were not found in the Data Marketplace.",
                    "danger",
                    "Not Found"
                );
            }
        } else {
            showToast(
                "The selected databases/tags were not found in the Data Marketplace.",
                "danger",
                "Not Found"
            );
        }
      } else {
        const successMsg = response.data.message || "Synchronization successful.";
        showToast(successMsg, 'success', 'Sync Completed');

        if (response.data.syncedResources) {
          onSyncUpdate(response.data.syncedResources);
          setStatusData(response.data.syncedResources);
        }
      }

    } catch (error) {
      let errorMsg = 'An error occurred during synchronization.';
      if (axios.isAxiosError(error) && error.code === 'ECONNABORTED') {
        errorMsg = `The synchronization timeout has been exceeded (${syncTimeout}ms).`;
      } else {
        errorMsg = error.response?.data?.message || errorMsg;
      }
      showToast(errorMsg, 'danger', 'Sync Error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const response = await axios.delete('delete_metadata', {
        data: {
          vdp_database_names: deleteVdbs,
          vdp_tag_names: deleteTags,
          delete_conflicting: deleteConflicting
        }
      });

      if (response.status === 204) {
          showToast(
            "No metadata found matching the specified criteria for deletion.", 
            'warning', 
            'No Content'
          );
      } else {
          const successMsg = response.data.message || "Deletion successful.";
          showToast(successMsg, 'success', 'Deletion Completed');

          if (response.data && response.data.syncedResources) {
            onSyncUpdate(response.data.syncedResources);
            setStatusData(response.data.syncedResources);
          }
      }

    } catch (error) {
      const errorMsg = error.response?.data?.message || 'An error occurred during deletion.';
      showToast(errorMsg, 'danger', 'Delete Error');
    } finally {
      setIsLoading(false);
    }
  };

  const renderResourceList = (resources) => {
    if (!resources || Object.keys(resources).length === 0) {
      return null;
    }
    return (
      <>
        {Object.entries(resources).map(([name, timestamp]) => (
          <ListGroup.Item key={name} className="d-flex justify-content-between align-items-center gap-3">
            <OverlayTrigger
              placement="top"
              delay={{ show: 250, hide: 400 }}
              overlay={
                <Tooltip id={`tooltip-${name}`}>
                  {name}
                </Tooltip>
              }
            >
              <code className="text-truncate" style={{ minWidth: 0 }}>
                {name}
              </code>
            </OverlayTrigger>
            <span style={{fontSize: '0.9em'}} className="text-nowrap flex-shrink-0">
              {formatTimestamp(timestamp)}
            </span>
          </ListGroup.Item>
        ))}
      </>
    );
  };

  const hasDatabases = statusData && statusData.DATABASE && Object.keys(statusData.DATABASE).length > 0;
  const hasTags = statusData && statusData.TAG && Object.keys(statusData.TAG).length > 0;
  const hasAnyData = hasDatabases || hasTags;

  const resetState = () => {
    setActiveTab('status');
    setSyncVdbs('');
    setSyncTags('');
    setIgnoreTags('');
    setDeleteVdbs('');
    setDeleteTags('');
    setDeleteConflicting(false);
  };

  const handleModalClose = () => {
    if (!isLoading) {
        resetState();
    }
    handleClose();
  };

  const renderFooterButtons = () => {
    if (activeTab === 'status') {
      return (
        <Button variant="light" onClick={handleModalClose}>
          Close
        </Button>
      );
    }

    if (activeTab === 'sync') {
      return (
        <>
          <Button variant="light" onClick={handleModalClose}>
            Cancel
          </Button>
          <Button variant="dark" type="submit" disabled={isLoading} form="sync-form">
            {isLoading ? (
              <>
                <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
                <span className="ms-2">Syncing...</span>
              </>
            ) : ( 'Sync' )}
          </Button>
        </>
      );
    }
    if (activeTab === 'delete') {
      return (
        <>
          <Button variant="light" onClick={handleModalClose}>
            Cancel
          </Button>
          <Button variant="danger" type="submit" disabled={isLoading} form="delete-form">
            {isLoading ? (
              <>
                <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
                <span className="ms-2">Deleting...</span>
              </>
            ) : ( 'Delete' )}
          </Button>
        </>
      );
    }
    return null;
  };

  return (
    <>
      <NotificationToast 
        show={toastConfig.show} 
        message={toastConfig.message} 
        variant={toastConfig.variant}
        title={toastConfig.title}
        duration={toastConfig.duration}
        onClose={handleToastClose} 
      />

      <Modal show={show} onHide={handleModalClose} centered data-bs-theme="light">
        <Modal.Header closeButton>
          <Modal.Title>Vector DB Management</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {!hasCredentials ? (
            <Alert variant="warning">
              AI SDK credentials are not configured. Please set the AI_SDK_USERNAME and AI_SDK_PASSWORD environment variables to use this feature.
            </Alert>
          ) : (
            <Tabs 
              activeKey={activeTab} 
              onSelect={(k) => !isLoading && setActiveTab(k)}
              id="vdb-management-tabs" 
              className="mb-3" 
              data-bs-theme="light"
            >
              <Tab eventKey="status" title="Vector DB Info" disabled={isLoading}>
                <p>This tab shows the synchronized VDBs and tags with their last synchronization date.</p>
                {hasDatabases && (
                  <>
                    <h5>Synchronized Databases</h5>
                    <div className="border rounded" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                      <ListGroup variant="flush">
                        {renderResourceList(statusData.DATABASE)}
                      </ListGroup>
                    </div>
                  </>
                )}
                {hasTags && (
                  <>
                    <h5 className={hasDatabases ? "mt-4" : ""}>Synchronized Tags</h5>
                    <div className="border rounded" style={{ maxHeight: '200px', overflowY: 'auto' }}>
                      <ListGroup variant="flush">
                        {renderResourceList(statusData.TAG)}
                      </ListGroup>
                    </div>
                  </>
                )}
                {!hasAnyData && (
                  <Alert variant="info" className="mt-3">
                    No synchronized resources found for your account. Use the 'Sync' tab to add them.
                  </Alert>
                )}
              </Tab>

              <Tab eventKey="sync" title="Sync" disabled={isLoading}>
                <Form id="sync-form" onSubmit={handleSyncSubmit}>
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
                  <div className="row">
                    <div className="col-md-6">
                        <Form.Group className="mb-3">
                            <Form.Label>Examples per Table</Form.Label>
                            <Form.Control
                            type="number"
                            min="0"
                            value={examplesPerTable}
                            onChange={(e) => setExamplesPerTable(parseInt(e.target.value))}
                            />
                        </Form.Group>
                    </div>
                  </div>
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
                </Form>
              </Tab>

              <Tab eventKey="delete" title="Delete" disabled={isLoading}>
                <Form id="delete-form" onSubmit={handleDeleteSubmit}>
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
                    <Form.Text>
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
                    <Form.Text>
                      If unchecked, entries linked to other synchronized sources will be preserved.
                    </Form.Text>
                  </Form.Group>
                </Form>
              </Tab>
            </Tabs>
          )}
        </Modal.Body>
        <Modal.Footer>
          {renderFooterButtons()}
        </Modal.Footer>
      </Modal>
    </>
  );
};

export default VectorDBSyncModal;