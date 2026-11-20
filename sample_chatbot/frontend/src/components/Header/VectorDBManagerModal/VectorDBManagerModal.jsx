import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { isAxiosError } from 'axios';
import { BaseModal, ConfirmationModal } from '../../Common/Modal';
import Spinner from 'react-bootstrap/Spinner';
import Alert from 'react-bootstrap/Alert';
import Tabs from 'react-bootstrap/Tabs';
import Tab from 'react-bootstrap/Tab';
import ListGroup from 'react-bootstrap/ListGroup';
import Form from 'react-bootstrap/Form';
import api from '../../../api/client';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';
import NotificationToast from "../../NotificationToast/NotificationToast";
import CustomTooltip from "../../CustomTooltip/CustomTooltip";
import ChipInput from '../../ChipInput/ChipInput';
import { useNumberFormat } from "../../../contexts/ConfigContext";
import './VectorDBManagerModal.css';

const formatTimestamp = (timestamp) => {
  if (!timestamp) return 'N/A';
  try {
    const date = new Date(timestamp);
    return date.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  } catch (error) {
    console.error('Error formatting timestamp:', error);
    return 'Invalid date';
  }
};

const VectorDBManagerModal = ({ show, handleClose, syncedResources, onResourcesUpdate, defaultTokenLimit = 0 }) => {
  const formatNumber = useNumberFormat();

  const [activeTab, setActiveTab] = useState('status');
  const [isLoading, setIsLoading] = useState(false);
  const [statusData, setStatusData] = useState(syncedResources || {});

  const [toastConfig, setToastConfig] = useState({
    show: false,
    message: '',
    variant: 'info',
    title: '',
    duration: 5000
  });

  const [syncVdbs, setSyncVdbs] = useState([]);
  const [syncTags, setSyncTags] = useState([]);
  const [ignoreTags, setIgnoreTags] = useState([]);
  const SYNC_INPUT_HELP_TEXT = "Type an item and press Enter, or paste a list separated by line breaks.";
  const [examplesPerTable, setExamplesPerTable] = useState(100);
  const [timeoutSeconds, setTimeoutSeconds] = useState(300);
  const [incremental, setIncremental] = useState(false);
  const [parallel, setParallel] = useState(true);
  const numericLimit = Number(defaultTokenLimit) || 0;
  const [isChunkingEnabled, setIsChunkingEnabled] = useState(numericLimit > 0);
  const [maxTokens, setMaxTokens] = useState(numericLimit > 0 ? numericLimit : 1000);

  const [selectedDatabases, setSelectedDatabases] = useState([]);
  const [selectedTags, setSelectedTags] = useState([]);
  const [deleteConflicting, setDeleteConflicting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState({
    show: false,
    dbCount: 0,
    tagCount: 0,
    deleteConflicting: false,
  });

  useEffect(() => {
    if (show) {
      setStatusData(syncedResources || {});
    }
  }, [show, syncedResources]);

  useEffect(() => {
    const limit = Number(defaultTokenLimit) || 0;
    setIsChunkingEnabled(limit > 0);
    setMaxTokens(limit > 0 ? limit : 1000);
  }, [defaultTokenLimit]);

  const showToast = (message, variant, title, duration = 5000) => {
    setToastConfig({ show: true, message, variant, title, duration });
  };

  const handleToastClose = () => {
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  const checkResourcesAlreadyExist = (requestedVdbs, requestedTags) => {
    const existingVdbs = statusData?.DATABASE ? Object.keys(statusData.DATABASE) : [];
    const existingTags = statusData?.TAG ? Object.keys(statusData.TAG) : [];
    return requestedVdbs.some(vdb => existingVdbs.includes(vdb)) || requestedTags.some(tag => existingTags.includes(tag));
  };

  const isTimeoutValid = timeoutSeconds !== '' && Number(timeoutSeconds) > 0;
  const isExamplesValid = examplesPerTable !== '' && Number(examplesPerTable) >= 0 && Number(examplesPerTable) <= 500;
  const isMaxTokensValid = !isChunkingEnabled || (maxTokens !== '' && Number(maxTokens) >= 1000);

  const handleSyncSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    const finalTimeoutSeconds = parseInt(timeoutSeconds, 10) || 300;
    const axiosTimeoutMs = finalTimeoutSeconds * 1000;

    try {
      const response = await api.post("sync_vdbs", {
        vdbs: syncVdbs,
        tags: syncTags,
        tags_to_ignore: ignoreTags,
        examples_per_table: examplesPerTable,
        timeout_seconds: finalTimeoutSeconds,
        incremental,
        parallel,
        embeddings_token_limit: isChunkingEnabled ? parseInt(maxTokens, 10) : 0
      }, { timeout: axiosTimeoutMs });

      if (response.status === 204) {
        if (incremental) {
          const existsLocally = checkResourcesAlreadyExist(syncVdbs, syncTags);
          showToast(
            existsLocally
              ? "You made an incremental request, but no updates have been made to the desired data since the last sync."
              : "The selected databases/tags were not found in the Data Marketplace.",
            existsLocally ? "warning" : "danger",
            existsLocally ? "No updates" : "Not found"
          );
        } else {
          showToast("The selected databases/tags were not found in the Data Marketplace.", "danger", "Not found");
        }
      } else {
        const errors = response.data.dataUsageErrors || [];
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
            const keyOrder = ['metadata_retrieval', 'vector_store_deletion', 'metadata_processing', 'vector_store_embedding', 'sample_data_processing', 'total_execution_time'];
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
              timingsMsg += `\n• ${formattedKey}: ${formatNumber(aggregatedTimings[key], 2)}s`;
            });
          }
        }

        if (response.data) {
          if (response.data.syncedResources) setStatusData(response.data.syncedResources);
          if (onResourcesUpdate) onResourcesUpdate(response.data);
        }

        setSyncVdbs([]);
        setSyncTags([]);
        setIgnoreTags([]);
        setActiveTab('status');

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
          showToast(`Sync completed, but with ${errors.length} warning(s):\n${errorList}${moreErrors}${timingsMsg}`, 'warning', 'Sync completed with warnings', 30000);
        } else {
          showToast((response.data.message || "Synchronization successful.") + timingsMsg, 'success', 'Sync completed', 15000);
        }
      }
    } catch (error) {
      let errorMsg = 'An error occurred during synchronization.';
      if (isAxiosError(error) && error.code === 'ECONNABORTED') {
        errorMsg = `The synchronization timeout has been exceeded (${finalTimeoutSeconds} seconds). Please sync again to ensure no metadata is missing.`;
      } else {
        errorMsg = error.response?.data?.detail || error.response?.data?.message || errorMsg;
      }
      showToast(errorMsg, 'danger', isAxiosError(error) && error.code === 'ECONNABORTED' ? 'Sync Timeout' : 'Sync Error', 10000);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectResource = (type, name, isChecked) => {
    if (type === 'DATABASE') {
      setSelectedDatabases(prev => isChecked ? [...prev, name] : prev.filter(item => item !== name));
    } else if (type === 'TAG') {
      setSelectedTags(prev => isChecked ? [...prev, name] : prev.filter(item => item !== name));
    }
  };

  const handleSelectAll = (type, isChecked) => {
    if (type === 'DATABASE') {
      setSelectedDatabases(isChecked ? Object.keys(statusData.DATABASE || {}) : []);
    } else if (type === 'TAG') {
      setSelectedTags(isChecked ? Object.keys(statusData.TAG || {}) : []);
    }
  };

  const handleRequestDelete = () => {
    setConfirmDelete({
      show: true,
      dbCount: selectedDatabases.length,
      tagCount: selectedTags.length,
      deleteConflicting,
    });
  };

  const handleDeleteSubmit = async () => {
    setConfirmDelete((prev) => ({ ...prev, show: false }));
    setIsLoading(true);
    try {
      const response = await api.delete("delete_metadata", {
        data: { vdp_database_names: selectedDatabases, vdp_tag_names: selectedTags, delete_conflicting: deleteConflicting }
      });

      if (response.status === 204) {
        showToast("No metadata found matching the specified criteria for deletion.", 'warning', 'No content');
      } else {
        showToast(response.data.message || "Deletion successful.", 'success', 'Deletion completed');
        if (response.data) {
          if (response.data.syncedResources) setStatusData(response.data.syncedResources);
          if (onResourcesUpdate) onResourcesUpdate(response.data);
        }
        setSelectedDatabases([]);
        setSelectedTags([]);
      }
    } catch (error) {
      showToast(error.response?.data?.message || 'An error occurred during deletion.', 'danger', 'Delete error');
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
      <div className="d-flex justify-content-between align-items-center mb-2 resource-section-header">
        <h5 className="m-0 rcc-modal-subtitle">{title}</h5>
        {allKeys.length > 1 && (
          <Form.Check
            type="checkbox"
            id={`select-all-${type}`}
            label={<span className="text-muted resource-timestamp">Select all</span>}
            checked={isAllSelected}
            ref={input => { if (input) input.indeterminate = isIndeterminate; }}
            onChange={(e) => handleSelectAll(type, e.target.checked)}
            disabled={isLoading}
            className="mb-0 small"
          />
        )}
      </div>
    );
  };

  const renderResourceList = (resources, type) => {
    if (!resources || Object.keys(resources).length === 0) return null;
    const selectedList = type === 'DATABASE' ? selectedDatabases : selectedTags;

    return (
      <>
        {Object.entries(resources).map(([name, timestamp]) => (
          <ListGroup.Item key={name} className="d-flex justify-content-between align-items-center gap-3">
            <div className="d-flex align-items-center gap-2">
              <Form.Check
                type="checkbox"
                className="m-0"
                id={`delete-${type}-${name}`}
                checked={selectedList.includes(name)}
                onChange={(e) => handleSelectResource(type, name, e.target.checked)}
                disabled={isLoading}
              />
              <OverlayTrigger
                placement="top"
                overlay={<Tooltip id={`tooltip-${name}`}>{name}</Tooltip>}
              >
                <code className="text-truncate resource-name-code" style={{ maxWidth: '240px' }}>{name}</code>
              </OverlayTrigger>
            </div>
            <span className="text-nowrap resource-timestamp">{formatTimestamp(timestamp)}</span>
          </ListGroup.Item>
        ))}
      </>
    );
  };

  const dbCount = statusData?.DATABASE ? Object.keys(statusData.DATABASE).length : 0;
  const tagCount = statusData?.TAG ? Object.keys(statusData.TAG).length : 0;
  const totalSources = dbCount + tagCount;
  const hasDatabases = dbCount > 0;
  const hasTags = tagCount > 0;
  const hasAnyData = hasDatabases || hasTags;
  const hasSelections = selectedDatabases.length > 0 || selectedTags.length > 0;

  const resetState = () => {
    setActiveTab('status');
    setSyncVdbs([]);
    setSyncTags([]);
    setIgnoreTags([]);
    setSelectedDatabases([]);
    setSelectedTags([]);
    setDeleteConflicting(false);
    setConfirmDelete((prev) => ({ ...prev, show: false }));
  };

  const handleOnExited = () => {
    if (!isLoading) resetState();
    setToastConfig((prev) => ({ ...prev, show: false }));
  };

  let footer = null;
  if (activeTab === 'status' && hasSelections) {
    footer = (
      <>
        <button type="button" className="rcc-ghost-btn" onClick={handleClose} disabled={isLoading}>Cancel</button>
        <button type="button" className="rcc-danger-btn" onClick={handleRequestDelete} disabled={isLoading}>
          {isLoading ? <Spinner animation="border" size="sm" /> : "Delete selected"}
        </button>
      </>
    );
  } else if (activeTab === 'sync') {
    footer = (
      <>
        <button type="button" className="rcc-ghost-btn" onClick={handleClose} disabled={isLoading}>Cancel</button>
        <button type="submit" className="rcc-primary-btn" form="sync-form" disabled={isLoading || !isTimeoutValid || !isExamplesValid || !isMaxTokensValid}>
          {isLoading ? <Spinner animation="border" size="sm" /> : "Sync"}
        </button>
      </>
    );
  }

  return (
    <>
      <BaseModal
        show={show}
        onHide={handleClose}
        onExited={handleOnExited}
        title="Vector DB Manager"
        headerBadges={
          <span className="rcc-quota">
            {totalSources} sources
          </span>
        }
        size="lg"
        fixedHeight
        backdrop="static"
        className="vdbsync-modal"
        footer={footer}
      >
          <Tabs activeKey={activeTab} onSelect={(k) => !isLoading && setActiveTab(k)} className="nav-tabs">
            <Tab eventKey="status" title="Manage resources" disabled={isLoading}>
              <div className="modal-scroll-container">
                <p className="text-muted small mb-4">View and inspect synced VDBs and tags or delete data models.</p>
                {hasDatabases && (
                  <div className="mb-4">
                    {renderSectionHeader('Synchronized VDBs', 'DATABASE')}
                    <div className="resource-list-container">
                      <ListGroup variant="flush">{renderResourceList(statusData.DATABASE, 'DATABASE')}</ListGroup>
                    </div>
                  </div>
                )}
                {hasTags && (
                  <div className="mb-4">
                    {renderSectionHeader('Synchronized tags', 'TAG')}
                    <div className="resource-list-container">
                      <ListGroup variant="flush">{renderResourceList(statusData.TAG, 'TAG')}</ListGroup>
                    </div>
                  </div>
                )}
                {hasSelections && (
                  <div className="mt-4 p-3 border rounded" style={{ background: "#f8fafc" }}>
                    <Form.Group>
                      <Form.Check
                        type="checkbox"
                        id="delete-conflicting-check"
                        className="small"
                        label={
                          <span className="d-inline-flex align-items-center gap-1">
                            Delete conflicting entries
                            <CustomTooltip id="tooltip-delete-conflicting" content="Delete cascade items attached to other selected synchronization components.">
                              <i className="bi bi-info-circle info-icon"></i>
                            </CustomTooltip>
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
                    No synchronized resources found. Use the "Sync" tab to add them.
                  </Alert>
                )}
              </div>
            </Tab>

            <Tab eventKey="sync" title="Sync" disabled={isLoading}>
              <div className="modal-scroll-container">
                <Form id="sync-form" onSubmit={handleSyncSubmit}>
                  <Form.Group className="mb-3">
                    <Form.Label className="small fw-semibold d-flex align-items-center">
                      VDBs to sync
                      <CustomTooltip id="tooltip-vdbs" content={SYNC_INPUT_HELP_TEXT}>
                        <i className="bi bi-info-circle info-icon ms-2" />
                      </CustomTooltip>
                    </Form.Label>
                    <ChipInput items={syncVdbs} setItems={setSyncVdbs} placeholder="VDB name + Enter..." />
                  </Form.Group>
                  <Form.Group className="mb-3">
                    <Form.Label className="small fw-semibold d-flex align-items-center">
                      Tags to sync
                      <CustomTooltip id="tooltip-tags" content={SYNC_INPUT_HELP_TEXT}>
                        <i className="bi bi-info-circle info-icon ms-2" />
                      </CustomTooltip>
                    </Form.Label>
                    <ChipInput items={syncTags} setItems={setSyncTags} placeholder="Tag name + Enter..." />
                  </Form.Group>
                  <Form.Group className="mb-3">
                    <Form.Label className="small fw-semibold d-flex align-items-center">
                      Tags to ignore
                      <CustomTooltip id="tooltip-ignore" content={SYNC_INPUT_HELP_TEXT}>
                        <i className="bi bi-info-circle info-icon ms-2" />
                      </CustomTooltip>
                    </Form.Label>
                    <ChipInput items={ignoreTags} setItems={setIgnoreTags} placeholder="Tags to ignore + Enter..." />
                  </Form.Group>

                  <div className="row g-2">
                    <div className="col-md-6">
                      <Form.Group className="mb-3">
                        <Form.Label className="small fw-semibold">Examples per table</Form.Label>
                        <Form.Control type="number" value={examplesPerTable} onChange={(e) => setExamplesPerTable(e.target.value === '' ? '' : parseInt(e.target.value))} isInvalid={examplesPerTable !== '' && !isExamplesValid} />
                      </Form.Group>
                    </div>
                    <div className="col-md-6">
                      <Form.Group className="mb-3">
                        <Form.Label className="small fw-semibold">Timeout (seconds)</Form.Label>
                        <Form.Control type="number" value={timeoutSeconds} onChange={(e) => setTimeoutSeconds(e.target.value === '' ? '' : parseInt(e.target.value))} isInvalid={timeoutSeconds !== '' && Number(timeoutSeconds) <= 0} />
                      </Form.Group>
                    </div>
                  </div>

                  <Form.Group className="mb-3">
                    <Form.Check
                      type="switch"
                      id="chunking-toggle"
                      className="small"
                      label={
                        <span className="d-inline-flex align-items-center gap-1">
                          Enable view chunking
                          <CustomTooltip id="tooltip-chunking" content="Check view token constraints and chunk long-running vector imports.">
                            <i className="bi bi-info-circle info-icon" />
                          </CustomTooltip>
                        </span>
                      }
                      checked={isChunkingEnabled}
                      onChange={(e) => setIsChunkingEnabled(e.target.checked)}
                    />
                  </Form.Group>

                  {isChunkingEnabled && (
                    <Form.Group className="mb-3" style={{ maxWidth: '180px' }}>
                      <Form.Label className="small fw-semibold">Max input tokens</Form.Label>
                      <Form.Control type="number" value={maxTokens} onChange={(e) => setMaxTokens(e.target.value === '' ? '' : parseInt(e.target.value))} isInvalid={!isMaxTokensValid} placeholder="e.g. 1000" />
                    </Form.Group>
                  )}

                  <Form.Group className="mb-3">
                    <Form.Check type="checkbox" className="small" label="Enable incremental loading" checked={incremental} onChange={(e) => setIncremental(e.target.checked)} />
                  </Form.Group>
                  <Form.Group className="mb-2">
                    <Form.Check type="checkbox" className="small" label="Enable parallel processing" checked={parallel} onChange={(e) => setParallel(e.target.checked)} />
                  </Form.Group>
                </Form>
              </div>
            </Tab>
          </Tabs>
      </BaseModal>

      <ConfirmationModal
        show={confirmDelete.show}
        onHide={() => setConfirmDelete((prev) => ({ ...prev, show: false }))}
        onConfirm={handleDeleteSubmit}
        nested
        title="Delete Synchronized Metadata"
        message={`Are you sure you want to delete the selected metadata (${[
          confirmDelete.dbCount > 0 ? `${confirmDelete.dbCount} database${confirmDelete.dbCount === 1 ? '' : 's'}` : null,
          confirmDelete.tagCount > 0 ? `${confirmDelete.tagCount} tag${confirmDelete.tagCount === 1 ? '' : 's'}` : null,
        ].filter(Boolean).join(' and ')}) from the vector database?${confirmDelete.deleteConflicting ? ' Views associated with multiple databases or tags will also be deleted.' : ''} This action cannot be undone.`}
        confirmLabel="Yes, delete"
      />

      <NotificationToast show={toastConfig.show} message={toastConfig.message} variant={toastConfig.variant} title={toastConfig.title} duration={toastConfig.duration} onClose={handleToastClose} />
    </>
  );
};

VectorDBManagerModal.propTypes = {
  show: PropTypes.bool.isRequired,
  handleClose: PropTypes.func.isRequired,
  syncedResources: PropTypes.object,
  onResourcesUpdate: PropTypes.func,
  defaultTokenLimit: PropTypes.number
};

export default VectorDBManagerModal;
