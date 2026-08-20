import React, { useState, useEffect } from 'react';
import { isAxiosError } from 'axios';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Tabs from 'react-bootstrap/Tabs';
import Tab from 'react-bootstrap/Tab';
import ListGroup from 'react-bootstrap/ListGroup';
import api from '../../api/client';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';
import NotificationToast from "../NotificationToast/NotificationToast";
import CustomTooltip from "../CustomTooltip/CustomTooltip";

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
    return 'Invalid date';
  }
};

const VectorDBSyncModal = ({ show, handleClose, syncedResources, onResourcesUpdate }) => {
  // Common state
  const [activeTab, setActiveTab] = useState('status');
  const [isLoading, setIsLoading] = useState(false);
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
  const [timeoutSeconds, setTimeoutSeconds] = useState(300);
  const [incremental, setIncremental] = useState(false);
  const [parallel, setParallel] = useState(true);

  // Delete state
  const [selectedDatabases, setSelectedDatabases] = useState([]);
  const [selectedTags, setSelectedTags] = useState([]);
  const [deleteConflicting, setDeleteConflicting] = useState(false);

  useEffect(() => {
    if (show) {
      setStatusData(syncedResources || {});
    }
  }, [show, syncedResources]);

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

  const isTimeoutValid = timeoutSeconds !== '' && Number(timeoutSeconds) > 0;
  const isExamplesValid = examplesPerTable !== '' && Number(examplesPerTable) >= 0 && Number(examplesPerTable) <= 500;

  const handleSyncSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);

    const processedVdbs = syncVdbs.split(',').map(vdb => vdb.trim()).filter(vdb => vdb);
    const processedTags = syncTags.split(',').map(tag => tag.trim()).filter(tag => tag);
    const processedIgnoreTags = ignoreTags.split(',').map(tag => tag.trim()).filter(tag => tag);

    const finalTimeoutSeconds = parseInt(timeoutSeconds, 10) || 300;
    const axiosTimeoutMs = finalTimeoutSeconds * 1000;

    try {
      const response = await api.post("sync_vdbs", {
        vdbs: processedVdbs,
        tags: processedTags,
        tags_to_ignore: processedIgnoreTags,
        examples_per_table: examplesPerTable,
        timeout_seconds: finalTimeoutSeconds,
        incremental,
        parallel
      }, {
        timeout: axiosTimeoutMs
      });

      if (response.status === 204) {
        if (incremental) {
            const existsLocally = checkResourcesAlreadyExist(processedVdbs, processedTags);
            if (existsLocally) {
                showToast(
                    "You made an incremental request, but no updates have been made to the desired data since the last sync.",
                    "warning",
                    "No updates",
                    10000
                );
            } else {
                showToast(
                    "The selected databases/tags were not found in the Data Marketplace.",
                    "danger",
                    "Not found"
                );
            }
        } else {
            showToast(
                "The selected databases/tags were not found in the Data Marketplace.",
                "danger",
                "Not found"
            );
        }
      } else {
        const errors = response.data.dataUsageErrors || [];

        // extract timings
        let timingsMsg = "";

        if (Array.isArray(response.data.timings) && response.data.timings.length > 0) {
          const aggregatedTimings = {};

          response.data.timings.forEach(timingObj => {
            Object.entries(timingObj).forEach(([key, value]) => {
              if (typeof value === 'number') {
                aggregatedTimings[key] = (aggregatedTimings[key] || 0) + value;
              }
            });
          });

          if (Object.keys(aggregatedTimings).length > 0) {
            timingsMsg += "\n\nTiming Breakdown (Aggregate):";

            const keyOrder = [
              'metadata_retrieval',
              'vector_store_deletion',
              'metadata_processing',
              'vector_store_embedding',
              'sample_data_processing',
              'total_execution_time'
            ];

            const sortedKeys = Object.keys(aggregatedTimings).sort((a, b) => {
              const indexA = keyOrder.indexOf(a);
              const indexB = keyOrder.indexOf(b);
              if (indexA === -1 && indexB === -1) return a.localeCompare(b);
              if (indexA === -1) return 1;
              if (indexB === -1) return -1;
              return indexA - indexB;
            });

            sortedKeys.forEach(key => {
              const formattedKey = key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
              timingsMsg += `\n• ${formattedKey}: ${Number(aggregatedTimings[key]).toFixed(2)}s`;
            });
          }
        } else if (response.data.timings && typeof response.data.timings === 'object' && !Array.isArray(response.data.timings)) {
          timingsMsg += "\n\nTiming Breakdown:";
          Object.entries(response.data.timings).forEach(([key, value]) => {
            const formattedKey = key.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
            timingsMsg += `\n• ${formattedKey}: ${Number(value).toFixed(2)}s`;
          });
        }

        if (response.data) {
          if (response.data.syncedResources) {
            setStatusData(response.data.syncedResources);
          }

          if (onResourcesUpdate) {
            onResourcesUpdate(response.data);
          }
        }

        setSyncVdbs('');
        setSyncTags('');
        setIgnoreTags('');
        setActiveTab('status'); 

        // append timings to toast
        if (errors.length > 0) {
          const formatError = (errObj) => {
            const msg = errObj.cause || 'Unknown error';

            if (errObj.databaseName && errObj.viewName) {
              const fieldInfo = errObj.fieldName ? `.${errObj.fieldName}` : '';
              return `• [${errObj.databaseName}.${errObj.viewName}${fieldInfo}] ${msg}`;
            }
            return `• ${msg}`;
          };

          const errorList = errors.slice(0, 3).map(formatError).join('\n');
          const moreErrors = errors.length > 3 ? `\n...and ${errors.length - 3} more.` : '';

          showToast(
              `Sync completed, but with ${errors.length} warning(s):\n${errorList}${moreErrors}${timingsMsg}`,
              'warning',
              'Sync completed with warnings',
              30000
          );
        } else {
          let successMsg = response.data.message || "Synchronization successful.";
          successMsg += timingsMsg;

          showToast(successMsg, 'success', 'Sync completed', 15000);
        }
      }

    } catch (error) {
      let errorMsg = 'An error occurred during synchronization.';
      if (isAxiosError(error) && error.code === 'ECONNABORTED') {
        errorMsg = `The synchronization timeout has been exceeded (${finalTimeoutSeconds} seconds). The request was cancelled before completion. It is recommended to synchronize again to ensure no metadata is missing.`;
      } else {
        errorMsg = error.response?.data?.message || errorMsg;
      }
      const toastTitle = isAxiosError(error) && error.code === 'ECONNABORTED' ? 'Sync Timeout' : 'Sync Error';
      showToast(errorMsg, 'danger', toastTitle, 10000);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectResource = (type, name, isChecked) => {
    if (type === 'DATABASE') {
      if (isChecked) {
        setSelectedDatabases(prev => [...prev, name]);
      } else {
        setSelectedDatabases(prev => prev.filter(item => item !== name));
      }
    } else if (type === 'TAG') {
      if (isChecked) {
        setSelectedTags(prev => [...prev, name]);
      } else {
        setSelectedTags(prev => prev.filter(item => item !== name));
      }
    }
  };

  const handleSelectAll = (type, isChecked) => {
    if (type === 'DATABASE') {
      if (isChecked) {
        setSelectedDatabases(Object.keys(statusData.DATABASE || {}));
      } else {
        setSelectedDatabases([]);
      }
    } else if (type === 'TAG') {
      if (isChecked) {
        setSelectedTags(Object.keys(statusData.TAG || {}));
      } else {
        setSelectedTags([]);
      }
    }
  };

  const handleDeleteSubmit = async () => {
    setIsLoading(true);

    try {
      const response = await api.delete("delete_metadata", {
        data: {
          vdp_database_names: selectedDatabases.join(','),
          vdp_tag_names: selectedTags.join(','),
          delete_conflicting: deleteConflicting
        }
      });

      if (response.status === 204) {
          showToast(
            "No metadata found matching the specified criteria for deletion.",
            'warning',
            'No content'
          );
      } else {
          const successMsg = response.data.message || "Deletion successful.";
          showToast(successMsg, 'success', 'Deletion completed');

          if (response.data) {
            if (response.data.syncedResources) {
              setStatusData(response.data.syncedResources);
            }

            if (onResourcesUpdate) {
              onResourcesUpdate(response.data);
            }
          }

          // Clear selection after successful deletion
          setSelectedDatabases([]);
          setSelectedTags([]);
      }

    } catch (error) {
      const errorMsg = error.response?.data?.message || 'An error occurred during deletion.';
      showToast(errorMsg, 'danger', 'Delete error');
    } finally {
      setIsLoading(false);
    }
  };

  const renderSectionHeader = (title, type) => {
    const resources = type === 'DATABASE' ? statusData.DATABASE : statusData.TAG;
    const selectedList = type === 'DATABASE' ? selectedDatabases : selectedTags;
    
    if (!resources) return null;
    
    const allKeys = Object.keys(resources);
    const isAllSelected = allKeys.length > 0 && selectedList.length === allKeys.length;
    const isIndeterminate = selectedList.length > 0 && selectedList.length < allKeys.length;

    return (
      <div className="d-flex justify-content-between align-items-center mb-2">
        <h5 className="m-0">{title}</h5>
        {allKeys.length > 1 && (
          <Form.Check
            type="checkbox"
            id={`select-all-${type}`}
            label={<span className="text-muted resource-timestamp">Select all</span>}
            checked={isAllSelected}
            ref={input => {
              if (input) input.indeterminate = isIndeterminate;
            }}
            onChange={(e) => handleSelectAll(type, e.target.checked)}
            disabled={isLoading}
            className="mb-0"
          />
        )}
      </div>
    );
  };

  const renderResourceList = (resources, type) => {
    if (!resources || Object.keys(resources).length === 0) {
      return null;
    }
    const selectedList = type === 'DATABASE' ? selectedDatabases : selectedTags;

    return (
      <>
        {Object.entries(resources).map(([name, timestamp]) => (
          <ListGroup.Item key={name} className="d-flex justify-content-between align-items-center gap-3">
            <div className="d-flex align-items-center gap-2 resource-name-container">
              <div> 
                <Form.Check
                  type="checkbox"
                  className="m-0"
                  id={`delete-${type}-${name}`}
                  checked={selectedList.includes(name)}
                  onChange={(e) => handleSelectResource(type, name, e.target.checked)}
                  disabled={isLoading}
                />
              </div>
              <OverlayTrigger
                placement="top"
                delay={{ show: 250, hide: 400 }}
                overlay={
                  <Tooltip id={`tooltip-${name}`}>
                    {name}
                  </Tooltip>
                }
              >
                <code className="text-truncate resource-name-code">
                  {name}
                </code>
              </OverlayTrigger>
            </div>
            <span className="text-nowrap flex-shrink-0 resource-timestamp">
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
  const hasSelections = selectedDatabases.length > 0 || selectedTags.length > 0;

  const resetState = () => {
    setActiveTab('status');
    setSyncVdbs('');
    setSyncTags('');
    setIgnoreTags('');
    setSelectedDatabases([]);
    setSelectedTags([]);
    setDeleteConflicting(false);
  };

  const handleOnExited = () => {
    if (!isLoading) {
      resetState();
    }
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const renderFooterButtons = () => {
    if (activeTab === 'status') {
      return (
        <>
          <Button variant="light" onClick={handleClose}>
            Close
          </Button>
          {hasSelections && (
            <Button variant="danger" onClick={handleDeleteSubmit} disabled={isLoading}>
              {isLoading ? (
                <>
                  <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" />
                  <span className="ms-2">Deleting...</span>
                </>
              ) : (
                'Delete selected'
              )}
            </Button>
          )}
        </>
      );
    }

    if (activeTab === 'sync') {
      return (
        <>
          <Button variant="light" onClick={handleClose}>
            Close
          </Button>
          <Button
              variant="dark"
              type="submit"
              disabled={isLoading || !isTimeoutValid || !isExamplesValid}
              form="sync-form"
          >
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

      <Modal
        show={show}
        onHide={handleClose}
        onExited={handleOnExited}
        centered
        data-bs-theme="light"
      >
        <Modal.Header closeButton>
          <Modal.Title>Vector DB Manager</Modal.Title>
        </Modal.Header>
        <Modal.Body>
            <Tabs
              activeKey={activeTab}
              onSelect={(k) => !isLoading && setActiveTab(k)}
              id="vdb-management-tabs"
              className="mb-3"
              data-bs-theme="light"
            >
              <Tab eventKey="status" title="Manage resources" disabled={isLoading}>
                <p className="text-muted mb-4">This tab shows your synchronized VDBs and tags. You can select items to delete them.</p>
                
                {hasDatabases && (
                  <div className="mb-4">
                    {renderSectionHeader('Synchronized VDBs', 'DATABASE')}
                    <div className="border rounded bg-white resource-list-container">
                      <ListGroup variant="flush">
                        {renderResourceList(statusData.DATABASE, 'DATABASE')}
                      </ListGroup>
                    </div>
                  </div>
                )}
                
                {hasTags && (
                  <div className="mb-4">
                    {renderSectionHeader('Synchronized tags', 'TAG')}
                    <div className="border rounded bg-white resource-list-container">
                      <ListGroup variant="flush">
                        {renderResourceList(statusData.TAG, 'TAG')}
                      </ListGroup>
                    </div>
                  </div>
                )}
                
                {hasSelections && (
                  <div className="mt-4 p-3 border rounded bg-light">
                    <Form.Group>
                      <Form.Check
                        type="checkbox"
                        id="delete-conflicting-check"
                        label={
                          <span className="d-inline-flex align-items-center">
                            <span className="fw-medium">Delete conflicting entries</span>
                            <span className="ms-2">
                              <CustomTooltip
                                id="tooltip-delete-conflicting"
                                content="If checked, entries linked to other synchronized sources will also be deleted. For example, if you synced both 'example_tag' and 'example_database', and you delete only 'example_tag', any views present in both will also be deleted."
                                delay={{ show: 200, hide: 300 }}
                              >
                                <i className="bi bi-info-circle info-icon"></i>
                              </CustomTooltip>
                            </span>
                          </span>
                        }
                        checked={deleteConflicting}
                        onChange={(e) => setDeleteConflicting(e.target.checked)}
                        disabled={isLoading}
                      />
                    </Form.Group>
                  </div>
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
                    <Form.Label>VDBs to sync (comma-separated)</Form.Label>
                    <Form.Control
                      type="text"
                      placeholder="Specify a comma-separated list of VDBs to sync"
                      value={syncVdbs}
                      onChange={(e) => setSyncVdbs(e.target.value)}
                    />
                  </Form.Group>
                  <Form.Group className="mb-3">
                    <Form.Label>Tags to sync (comma-separated)</Form.Label>
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
                            <Form.Label>Examples per table</Form.Label>
                            <Form.Control
                                type="number"
                                min="0"
                                max="500"
                                value={examplesPerTable}
                                isInvalid={examplesPerTable !== '' && !isExamplesValid}
                                onChange={(e) => setExamplesPerTable(e.target.value === '' ? '' : parseInt(e.target.value))}
                            />
                            <Form.Control.Feedback type="invalid">
                                Must be between 0 and 500.
                            </Form.Control.Feedback>
                        </Form.Group>
                    </div>
                    <div className="col-md-6">
                        <Form.Group className="mb-3">
                          <Form.Label>Timeout (seconds)</Form.Label>
                          <Form.Control
                              type="number"
                              min="1"
                              value={timeoutSeconds}
                              isInvalid={timeoutSeconds !== '' && Number(timeoutSeconds) <= 0}
                              onChange={(e) => setTimeoutSeconds(e.target.value === '' ? '' : parseInt(e.target.value))}
                          />
                          <Form.Control.Feedback type="invalid">
                              Must be greater than 0.
                          </Form.Control.Feedback>
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
            </Tabs>
        </Modal.Body>
        <Modal.Footer>
          {renderFooterButtons()}
        </Modal.Footer>
      </Modal>
    </>
  );
};

export default VectorDBSyncModal;
